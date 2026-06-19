from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import Meal, FoodItem, DailyNutrition, UserProfile
from app.auth import get_current_user
from datetime import date
import httpx

router = APIRouter(prefix="/diet", tags=["diet"])
templates = Jinja2Templates(directory="app/templates")

OFF_BASE = "https://world.openfoodfacts.org"


@router.get("", response_class=HTMLResponse)
async def diet_page(
    request: Request,
    fecha: str = None,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    today = date.fromisoformat(fecha) if fecha else date.today()

    result = await db.execute(
        select(Meal)
        .where(Meal.user_id == user.id, Meal.fecha == today)
        .options(selectinload(Meal.foods))
        .order_by(Meal.hora)
    )
    meals = result.scalars().all()

    result = await db.execute(
        select(DailyNutrition)
        .where(DailyNutrition.user_id == user.id, DailyNutrition.fecha == today)
    )
    goals = result.scalar_one_or_none()

    totals = {"calorias": 0, "proteinas": 0, "carbs": 0, "grasas": 0}
    for meal in meals:
        for food in meal.foods:
            totals["calorias"] += (food.calorias or 0) * (food.cantidad / 100)
            totals["proteinas"] += (food.proteinas or 0) * (food.cantidad / 100)
            totals["carbs"] += (food.carbs or 0) * (food.cantidad / 100)
            totals["grasas"] += (food.grasas or 0) * (food.cantidad / 100)

    meal_types = ["Desayuno", "Comida", "Cena", "Snack", "Postre", "Bebida"]

    return templates.TemplateResponse(request, "diet/index.html", {
        "user": user, "meals": meals, "goals": goals,
        "totals": totals, "fecha": today, "meal_types": meal_types,
    })


@router.get("/add/{tipo}", response_class=HTMLResponse)
async def add_meal_page(
    request: Request,
    tipo: str,
    fecha: str = None,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    today = date.fromisoformat(fecha) if fecha else date.today()
    return templates.TemplateResponse(request, "diet/add_meal.html", {
        "user": user, "tipo": tipo, "fecha": today,
    })


@router.post("/add/{tipo}")
async def add_meal(
    request: Request,
    tipo: str,
    fecha: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    today = date.fromisoformat(fecha) if fecha else date.today()
    meal = Meal(user_id=user.id, fecha=today, tipo=tipo)
    db.add(meal)
    await db.commit()
    await db.refresh(meal)
    return RedirectResponse(url=f"/diet/meal/{meal.id}/add-food", status_code=302)


@router.get("/meal/{meal_id}/add-food", response_class=HTMLResponse)
async def add_food_page(
    request: Request,
    meal_id: int,
    query: str = "",
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(Meal).where(Meal.id == meal_id, Meal.user_id == user.id)
    )
    meal = result.scalar_one_or_none()
    if not meal:
        raise HTTPException(status_code=404, detail="Comida no encontrada")

    foods = []
    if query:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{OFF_BASE}/cgi/search.pl",
                    params={
                        "search_terms": query,
                        "search_simple": 1,
                        "action": "process",
                        "json": 1,
                        "page_size": 20,
                        "lang": "es",
                    },
                    timeout=10,
                )
                data = resp.json()
                for p in data.get("products", []):
                    nut = p.get("nutriments", {})
                    foods.append({
                        "id": p.get("id") or p.get("code", ""),
                        "name": p.get("product_name", "Sin nombre"),
                        "image": p.get("image_front_thumb_url", ""),
                        "calorias": nut.get("energy-kcal_100g", 0),
                        "proteinas": nut.get("proteins_100g", 0),
                        "carbs": nut.get("carbohydrates_100g", 0),
                        "grasas": nut.get("fat_100g", 0),
                    })
            except Exception:
                pass

    return templates.TemplateResponse(request, "diet/add_food.html", {
        "user": user, "meal": meal, "foods": foods, "query": query,
    })


@router.post("/meal/{meal_id}/add-food")
async def add_food_to_meal(
    meal_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    data = await request.form()
    fi = FoodItem(
        meal_id=meal_id,
        food_name=data["food_name"],
        cantidad=float(data.get("cantidad", 100)),
        calorias=float(data.get("calorias", 0)),
        proteinas=float(data.get("proteinas", 0)),
        carbs=float(data.get("carbs", 0)),
        grasas=float(data.get("grasas", 0)),
    )
    db.add(fi)
    await db.commit()
    return RedirectResponse(url="/diet", status_code=302)


@router.post("/goals")
async def update_goals(
    request: Request,
    calorias: float = Form(2000),
    proteinas: float = Form(150),
    carbs: float = Form(250),
    grasas: float = Form(65),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    today = date.today()
    result = await db.execute(
        select(DailyNutrition).where(
            DailyNutrition.user_id == user.id,
            DailyNutrition.fecha == today,
        )
    )
    goals = result.scalar_one_or_none()
    if goals:
        goals.calorias_objetivo = calorias
        goals.proteinas_objetivo = proteinas
        goals.carbs_objetivo = carbs
        goals.grasas_objetivo = grasas
    else:
        goals = DailyNutrition(
            user_id=user.id, fecha=today,
            calorias_objetivo=calorias,
            proteinas_objetivo=proteinas,
            carbs_objetivo=carbs,
            grasas_objetivo=grasas,
        )
        db.add(goals)
    await db.commit()
    return RedirectResponse(url="/diet", status_code=302)
