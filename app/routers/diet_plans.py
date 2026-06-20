import re
import httpx
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import DietPlan, DietPlanMeal, DietPlanFood, DietPlanAssignment, UserProfile
from app.auth import get_current_user
from datetime import date, timedelta

router = APIRouter(prefix="/diet-plans", tags=["diet-plans"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def list_plans(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(DietPlan)
        .where(DietPlan.user_id == user.id)
        .options(selectinload(DietPlan.meals).selectinload(DietPlanMeal.foods))
        .order_by(DietPlan.created_at.desc())
    )
    plans = result.scalars().all()

    # Get assignments for this week
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_days = [week_start + timedelta(days=i) for i in range(7)]

    result = await db.execute(
        select(DietPlanAssignment)
        .where(
            DietPlanAssignment.user_id == user.id,
            DietPlanAssignment.fecha >= week_start,
            DietPlanAssignment.fecha < week_start + timedelta(days=7),
        )
        .options(selectinload(DietPlanAssignment.plan))
    )
    assignments = result.scalars().all()
    assignment_map = {a.fecha.isoformat(): a for a in assignments}

    return templates.TemplateResponse(request, "diet_plans/list.html", {
        "user": user, "plans": plans,
        "week_days": week_days, "assignment_map": assignment_map,
        "today": today,
    })


@router.get("/new", response_class=HTMLResponse)
async def new_plan_page(
    request: Request,
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    return templates.TemplateResponse(request, "diet_plans/new.html", {
        "user": user, "meal_types": TIPOS_COMIDA
    })


TIPOS_COMIDA = ["Desayuno", "Almuerzo", "Comida", "Merienda", "Cena", "Snack", "Postre"]


def parse_diet_text(text: str):
    meals_parsed = []
    text = text.strip()

    parts = re.split(
        r'(?:^|\n)\s*(Desayuno|Almuerzo|Comida|Merienda|Cena|Snack|Postre)\s*[:\-]?\s*',
        text, flags=re.IGNORECASE | re.MULTILINE
    )

    current_tipo = None
    current_content = ""

    for part in parts:
        part = part.strip()
        if not part:
            continue
        lower = part.lower()
        if lower in ("desayuno", "almuerzo", "comida", "merienda", "cena", "snack", "postre"):
            if current_tipo and current_content:
                meals_parsed.append((current_tipo, current_content))
            current_tipo = part.capitalize()
            current_content = ""
        else:
            if current_tipo:
                current_content += " " + part if current_content else part

    if current_tipo and current_content:
        meals_parsed.append((current_tipo, current_content))

    result = []
    for tipo, content in meals_parsed:
        content = re.sub(r'\s*\*\s*', ' ', content)
        content = re.sub(r'\s*\.\s*$', '', content)
        items = re.split(r'\s*\+\s*', content)
        foods = []
        for item in items:
            item = item.strip()
            if not item or item.lower() in ("", "y"):
                continue
            qty_match = re.search(
                r'(\d+(?:[.,]\d+)?)\s*(gramos|g|gr|ml|unidad|unidades|cucharada|cucharadas|taza|tazas|kg|litro|l)\s*(?:de\s+)?',
                item, re.IGNORECASE
            )
            if qty_match:
                qty_str = qty_match.group(1).replace(",", ".")
                qty = float(qty_str)
                unit = qty_match.group(2).lower()
                unit_map = {"g": "g", "gr": "g", "gramos": "g", "ml": "ml", "litro": "ml", "l": "ml",
                            "unidad": "unidad", "unidades": "unidad",
                            "cucharada": "cucharada", "cucharadas": "cucharada",
                            "taza": "taza", "tazas": "taza", "kg": "g"}
                qty = qty * 1000 if unit == "kg" else qty
                unit_final = unit_map.get(unit, "g")
                name = item[:qty_match.start()] + item[qty_match.end():]
                name = re.sub(r'\s+', ' ', name).strip().strip(',').strip()
                name = re.sub(r'\s*[oO]\s*', ' / ', name)
                if not name:
                    continue
                foods.append({"name": name, "cantidad": qty, "unidad": unit_final})
            else:
                food_name = re.sub(r'\s*[oO]\s*', ' / ', item).strip()
                if food_name.lower() in ("y",):
                    continue
                foods.append({"name": food_name, "cantidad": None, "unidad": "g"})
        if foods:
            result.append({"tipo": tipo, "foods": foods})
    return result


@router.get("/import", response_class=HTMLResponse)
async def import_page(
    request: Request,
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    return templates.TemplateResponse(request, "diet_plans/import.html", {
        "user": user
    })


@router.post("/import")
async def import_plan(
    request: Request,
    nombre: str = Form(...),
    texto: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    plan = DietPlan(user_id=user.id, nombre=nombre, descripcion="Importado automáticamente")
    db.add(plan)
    await db.flush()

    meals_data = parse_diet_text(texto)
    for idx, meal_data in enumerate(meals_data):
        meal = DietPlanMeal(
            diet_plan_id=plan.id,
            tipo=meal_data["tipo"],
            orden=idx,
        )
        db.add(meal)
        await db.flush()
        for food_data in meal_data["foods"]:
            food = DietPlanFood(
                diet_plan_meal_id=meal.id,
                food_name=food_data["name"],
                cantidad=food_data["cantidad"],
                unidad=food_data["unidad"],
            )
            db.add(food)

    await db.commit()
    return RedirectResponse(url=f"/diet-plans/{plan.id}/edit", status_code=302)


@router.post("/new")
async def create_plan(
    request: Request,
    nombre: str = Form(...),
    descripcion: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    plan = DietPlan(user_id=user.id, nombre=nombre, descripcion=descripcion)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return RedirectResponse(url=f"/diet-plans/{plan.id}/edit", status_code=302)


@router.get("/{plan_id}", response_class=HTMLResponse)
async def view_plan(
    request: Request,
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(DietPlan)
        .where(DietPlan.id == plan_id, DietPlan.user_id == user.id)
        .options(selectinload(DietPlan.meals).selectinload(DietPlanMeal.foods))
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    return templates.TemplateResponse(request, "diet_plans/view.html", {
        "user": user, "plan": plan
    })


@router.get("/{plan_id}/edit", response_class=HTMLResponse)
async def edit_plan_page(
    request: Request,
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(DietPlan)
        .where(DietPlan.id == plan_id, DietPlan.user_id == user.id)
        .options(selectinload(DietPlan.meals).selectinload(DietPlanMeal.foods))
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    return templates.TemplateResponse(request, "diet_plans/edit.html", {
        "user": user, "plan": plan, "meal_types": TIPOS_COMIDA
    })


@router.post("/{plan_id}/add-meal")
async def add_meal_to_plan(
    request: Request,
    plan_id: int,
    tipo: str = Form(...),
    notas: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(DietPlan).where(DietPlan.id == plan_id, DietPlan.user_id == user.id)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    result = await db.execute(
        select(DietPlanMeal)
        .where(DietPlanMeal.diet_plan_id == plan_id)
        .order_by(DietPlanMeal.orden.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    orden = (last.orden + 1) if last else 0

    meal = DietPlanMeal(diet_plan_id=plan_id, tipo=tipo, notas=notas, orden=orden)
    db.add(meal)
    await db.commit()
    return RedirectResponse(url=f"/diet-plans/{plan_id}/edit", status_code=302)


@router.post("/{plan_id}/meals/{meal_id}/add-food")
async def add_food_to_meal(
    request: Request,
    plan_id: int,
    meal_id: int,
    food_name: str = Form(...),
    cantidad: float = Form(0),
    unidad: str = Form("g"),
    calorias: float = Form(0),
    proteinas: float = Form(0),
    carbs: float = Form(0),
    grasas: float = Form(0),
    notas: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    food = DietPlanFood(
        diet_plan_meal_id=meal_id,
        food_name=food_name,
        cantidad=cantidad or None,
        unidad=unidad,
        calorias=calorias or None,
        proteinas=proteinas or None,
        carbs=carbs or None,
        grasas=grasas or None,
        notas=notas or None,
    )
    db.add(food)
    await db.commit()
    return RedirectResponse(url=f"/diet-plans/{plan_id}/edit", status_code=302)


@router.post("/{plan_id}/meals/{meal_id}/foods/{food_id}/lookup")
async def lookup_food_macros(
    plan_id: int,
    meal_id: int,
    food_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(select(DietPlanFood).where(DietPlanFood.id == food_id))
    food = result.scalar_one_or_none()
    if not food:
        raise HTTPException(status_code=404, detail="Alimento no encontrado")

    search_name = food.food_name.split(" / ")[0].strip().lower()
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://world.openfoodfacts.org/cgi/search.pl",
                params={
                    "search_terms": search_name,
                    "search_simple": 1,
                    "action": "process",
                    "json": 1,
                    "page_size": 3,
                    "lang": "es",
                },
                timeout=10,
            )
            data = resp.json()
            for p in data.get("products", []):
                nut = p.get("nutriments", {})
                cal = nut.get("energy-kcal_100g")
                if cal and cal > 0:
                    food.calorias = cal
                    food.proteinas = nut.get("proteins_100g")
                    food.carbs = nut.get("carbohydrates_100g")
                    food.grasas = nut.get("fat_100g")
                    break
        except Exception:
            pass

    await db.commit()
    return RedirectResponse(url=f"/diet-plans/{plan_id}/edit", status_code=302)


@router.post("/{plan_id}/meals/{meal_id}/delete-food/{food_id}")
async def delete_food(
    plan_id: int,
    meal_id: int,
    food_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    await db.execute(
        delete(DietPlanFood).where(
            DietPlanFood.id == food_id,
            DietPlanFood.diet_plan_meal_id == meal_id,
        )
    )
    await db.commit()
    return RedirectResponse(url=f"/diet-plans/{plan_id}/edit", status_code=302)


@router.post("/{plan_id}/delete-meal/{meal_id}")
async def delete_meal(
    plan_id: int,
    meal_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    await db.execute(
        delete(DietPlanMeal).where(
            DietPlanMeal.id == meal_id,
            DietPlanMeal.diet_plan_id == plan_id,
        )
    )
    await db.commit()
    return RedirectResponse(url=f"/diet-plans/{plan_id}/edit", status_code=302)


@router.post("/{plan_id}/delete")
async def delete_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    await db.execute(
        delete(DietPlan).where(DietPlan.id == plan_id, DietPlan.user_id == user.id)
    )
    await db.commit()
    return RedirectResponse(url="/diet-plans", status_code=302)


@router.post("/assign")
async def assign_plan_to_date(
    request: Request,
    plan_id: int = Form(...),
    fecha: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    target_date = date.fromisoformat(fecha)

    result = await db.execute(
        select(DietPlanAssignment).where(
            DietPlanAssignment.user_id == user.id,
            DietPlanAssignment.fecha == target_date,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.diet_plan_id = plan_id
    else:
        assignment = DietPlanAssignment(
            user_id=user.id, diet_plan_id=plan_id, fecha=target_date
        )
        db.add(assignment)

    await db.commit()
    return RedirectResponse(url="/diet-plans", status_code=302)


@router.post("/unassign/{assignment_id}")
async def unassign_plan(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    await db.execute(
        delete(DietPlanAssignment).where(
            DietPlanAssignment.id == assignment_id,
            DietPlanAssignment.user_id == user.id,
        )
    )
    await db.commit()
    return RedirectResponse(url="/diet-plans", status_code=302)
