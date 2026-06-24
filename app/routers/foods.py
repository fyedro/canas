import httpx
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from urllib.parse import quote
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import FoodCatalog, FoodItem, Meal, RecipeIngredient, UserProfile, FOOD_GROUPS
from app.auth import get_current_user

router = APIRouter(prefix="/foods", tags=["foods"])
templates = Jinja2Templates(directory="app/templates")
OFF_BASE = "https://es.openfoodfacts.org"


async def search_off(query: str) -> list:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{OFF_BASE}/cgi/search.pl",
                params={
                    "search_terms": query,
                    "search_simple": 1,
                    "action": "process",
                    "json": 1,
                    "page_size": 30,
                    "lang": "es",
                },
                timeout=10,
            )
            data = resp.json()
            results = []
            for p in data.get("products", []):
                nut = p.get("nutriments", {})
                results.append({
                    "code": p.get("code", ""),
                    "name": p.get("product_name", "Sin nombre"),
                    "image": p.get("image_front_thumb_url", ""),
                    "calorias": nut.get("energy-kcal_100g", 0),
                    "proteinas": nut.get("proteins_100g", 0),
                    "carbs": nut.get("carbohydrates_100g", 0),
                    "grasas": nut.get("fat_100g", 0),
                })
            return results
        except Exception:
            return []


BASIC_FOODS = [
    # Verduras
    ("Tomate", "Verdura", 18, 0.9, 3.9, 0.2),
    ("Pimiento rojo", "Verdura", 31, 1.0, 6.0, 0.3),
    ("Pimiento verde", "Verdura", 20, 0.9, 4.6, 0.2),
    ("Cebolla", "Verdura", 40, 1.1, 9.3, 0.1),
    ("Ajo", "Verdura", 149, 6.4, 33.1, 0.5),
    ("Zanahoria", "Verdura", 41, 0.9, 9.6, 0.2),
    ("Berenjena", "Verdura", 25, 1.0, 5.9, 0.2),
    ("Calabacín", "Verdura", 17, 1.2, 3.1, 0.3),
    ("Lechuga", "Verdura", 15, 1.4, 2.9, 0.2),
    ("Espinaca", "Verdura", 23, 2.9, 3.6, 0.4),
    ("Brócoli", "Verdura", 34, 2.8, 7.0, 0.4),
    ("Coliflor", "Verdura", 25, 1.9, 5.0, 0.3),
    ("Pepino", "Verdura", 15, 0.7, 3.6, 0.1),
    # Frutas
    ("Manzana", "Fruta", 52, 0.3, 14.0, 0.2),
    ("Plátano", "Fruta", 89, 1.1, 22.8, 0.3),
    ("Naranja", "Fruta", 47, 0.9, 11.8, 0.1),
    ("Limón", "Fruta", 29, 1.1, 9.3, 0.3),
    ("Fresa", "Fruta", 32, 0.7, 7.7, 0.3),
    ("Uva", "Fruta", 69, 0.7, 18.1, 0.2),
    ("Aguacate", "Fruta", 160, 2.0, 8.5, 14.7),
    ("Pera", "Fruta", 57, 0.4, 15.2, 0.1),
    # Carnes
    ("Pechuga de pollo", "Carnes", 165, 31.0, 0.0, 3.6),
    ("Muslo de pollo", "Carnes", 172, 26.0, 0.0, 7.2),
    ("Pechuga de pavo", "Carnes", 135, 29.0, 0.0, 1.5),
    ("Carne picada de ternera", "Carnes", 250, 18.0, 0.0, 20.0),
    ("Solomillo de cerdo", "Carnes", 143, 26.0, 0.0, 3.5),
    ("Lomo de cerdo", "Carnes", 200, 21.0, 0.0, 12.0),
    ("Ternera para guisar", "Carnes", 180, 25.0, 0.0, 8.0),
    # Pescados
    ("Lubina", "Pescados", 97, 18.0, 0.0, 2.6),
    ("Dorada", "Pescados", 96, 18.0, 0.0, 2.5),
    ("Salmón", "Pescados", 208, 20.4, 0.0, 13.4),
    ("Atún claro al natural (lata)", "Pescados", 120, 26.0, 0.0, 1.5),
    ("Atún en aceite vegetal (lata)", "Pescados", 210, 24.0, 0.0, 12.0),
    ("Merluza", "Pescados", 82, 18.0, 0.0, 0.7),
    ("Bacalao", "Pescados", 82, 17.9, 0.0, 0.7),
    ("Gamba", "Pescados", 85, 17.6, 0.0, 0.6),
    # Huevos y lácteos
    ("Huevo entero", "Huevos", 155, 13.0, 1.1, 11.0),
    ("Clara de huevo", "Huevos", 52, 11.0, 0.7, 0.2),
    ("Yema de huevo", "Huevos", 322, 16.0, 3.6, 27.0),
    ("Leche entera", "Lácteos", 61, 3.3, 4.7, 3.3),
    ("Leche semidesnatada", "Lácteos", 46, 3.3, 4.8, 1.6),
    ("Leche desnatada", "Lácteos", 34, 3.4, 5.0, 0.1),
    ("Queso fresco", "Lácteos", 174, 18.0, 3.0, 10.0),
    ("Queso parmesano", "Lácteos", 431, 38.0, 4.1, 29.0),
    ("Yogur natural", "Lácteos", 61, 3.5, 4.7, 3.3),
    # Legumbres
    ("Garbanzo cocido", "Legumbres", 139, 8.9, 22.5, 2.1),
    ("Lenteja cocida", "Legumbres", 116, 9.0, 20.1, 0.4),
    ("Alubia cocida", "Legumbres", 127, 8.7, 22.8, 0.5),
    ("Judía verde", "Verdura", 31, 1.8, 7.0, 0.1),
    ("Guisantes en conserva (lata)", "Legumbres", 80, 5.0, 12.0, 0.5),
    # Cereales
    ("Arroz blanco cocido", "Cereales", 130, 2.7, 28.2, 0.3),
    ("Arroz integral cocido", "Cereales", 111, 2.6, 23.0, 0.9),
    ("Pasta cocida", "Cereales", 131, 5.0, 26.0, 1.1),
    ("Pan blanco", "Cereales", 265, 9.0, 49.0, 3.2),
    ("Pan integral", "Cereales", 247, 10.0, 45.0, 3.4),
    ("Avena copos", "Cereales", 389, 16.9, 66.3, 6.9),
    ("Quinoa cocida", "Cereales", 120, 4.4, 21.3, 1.9),
    ("Cuscús cocido", "Cereales", 112, 3.8, 23.2, 0.2),
    # Aceites y grasas
    ("Aceite de oliva virgen extra", "Aceites", 884, 0.0, 0.0, 100.0),
    ("Aceite de girasol", "Aceites", 884, 0.0, 0.0, 100.0),
    ("Mantequilla", "Aceites", 717, 0.9, 0.1, 81.0),
    # Frutos secos
    ("Almendra", "Frutos secos", 579, 21.2, 21.6, 49.9),
    ("Nuez", "Frutos secos", 654, 15.2, 13.7, 65.2),
    ("Anacardo", "Frutos secos", 553, 18.2, 30.2, 43.9),
    ("Cacahuete", "Frutos secos", 567, 25.8, 16.1, 49.2),
    ("Nueces de Brasil", "Frutos secos", 659, 14.3, 11.7, 67.1),
]


@router.get("", response_class=HTMLResponse)
async def list_foods(
    request: Request,
    search: str = Query(""),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    # Always add missing basic foods
    existing_names = {
        r[0] for r in (await db.execute(
            select(FoodCatalog.food_name).where(FoodCatalog.user_id == user.id)
        )).all()
    }
    added = 0
    for name, grupo, cal, pro, carbs, gras in BASIC_FOODS:
        if name not in existing_names:
            db.add(FoodCatalog(
                user_id=user.id, food_name=name, grupo=grupo,
                calorias=cal, proteinas=pro, carbs=carbs, grasas=gras,
            ))
            existing_names.add(name)
            added += 1
    if added:
        await db.commit()

    off_results = []
    if search:
        off_results = await search_off(search)

    result = await db.execute(
        select(FoodCatalog).where(FoodCatalog.user_id == user.id)
        .order_by(FoodCatalog.grupo, FoodCatalog.food_name)
    )
    my_foods = result.scalars().all()

    grouped = {}
    for f in my_foods:
        g = f.grupo or "Otros"
        grouped.setdefault(g, []).append(f)

    return templates.TemplateResponse(request, "foods/list.html", {
        "user": user, "my_foods": my_foods, "grouped": grouped,
        "off_results": off_results, "search": search,
        "food_groups": FOOD_GROUPS,
    })


@router.post("/save-off")
async def save_off_food(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    data = await request.form()
    existing = await db.execute(
        select(FoodCatalog).where(
            FoodCatalog.user_id == user.id,
            FoodCatalog.barcode == data.get("code", ""),
        ).limit(1)
    )
    if not existing.scalar_one_or_none():
        food = FoodCatalog(
            user_id=user.id,
            food_name=data["name"],
            calorias=float(data.get("calorias", 0)),
            proteinas=float(data.get("proteinas", 0)),
            carbs=float(data.get("carbs", 0)),
            grasas=float(data.get("grasas", 0)),
            imagen_url=data.get("image", "") or None,
            barcode=data.get("code", "") or None,
        )
        db.add(food)
        await db.commit()
    search_q = quote(data.get('name', ''))
    return RedirectResponse(url=f"/foods?search={search_q}", status_code=302)


@router.get("/new", response_class=HTMLResponse)
async def new_food_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    return templates.TemplateResponse(request, "foods/new.html", {
        "user": user, "food_groups": FOOD_GROUPS,
    })


@router.post("/new")
async def create_food(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    data = await request.form()
    food = FoodCatalog(
        user_id=user.id,
        food_name=data["food_name"],
        grupo=data.get("grupo", "") or None,
        calorias=float(data.get("calorias", 0)),
        proteinas=float(data.get("proteinas", 0)),
        carbs=float(data.get("carbs", 0)),
        grasas=float(data.get("grasas", 0)),
        porcion=float(data.get("porcion", 0) or 0) or None,
    )
    db.add(food)
    await db.commit()
    return RedirectResponse(url=f"/foods?search={quote(food.food_name)}", status_code=302)


@router.get("/{food_id}/edit", response_class=HTMLResponse)
async def edit_food_page(
    request: Request,
    food_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    result = await db.execute(
        select(FoodCatalog).where(
            FoodCatalog.id == food_id, FoodCatalog.user_id == user.id
        ).options(selectinload(FoodCatalog.recipe_ingredients))
    )
    food = result.scalar_one_or_none()
    if not food:
        raise HTTPException(status_code=404)

    catalog = (await db.execute(
        select(FoodCatalog).where(FoodCatalog.user_id == user.id)
        .order_by(FoodCatalog.food_name)
    )).scalars().all()

    return templates.TemplateResponse(request, "foods/edit.html", {
        "user": user, "food": food, "catalog": catalog,
        "food_groups": FOOD_GROUPS,
    })


@router.post("/{food_id}/edit")
async def edit_food(
    request: Request,
    food_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    result = await db.execute(
        select(FoodCatalog).where(
            FoodCatalog.id == food_id, FoodCatalog.user_id == user.id
        )
    )
    food = result.scalar_one_or_none()
    if not food:
        raise HTTPException(status_code=404)

    data = await request.form()
    food.food_name = data["food_name"]
    food.grupo = data.get("grupo", "") or None
    food.calorias = float(data.get("calorias", 0))
    food.proteinas = float(data.get("proteinas", 0))
    food.carbs = float(data.get("carbs", 0))
    food.grasas = float(data.get("grasas", 0))
    food.porcion = float(data.get("porcion", 0) or 0) or None

    # Rebuild recipe ingredients
    ingredient_ids = data.getlist("ingredient_id")
    ingredient_qty = data.getlist("ingredient_qty")
    has_ingredients = ingredient_ids and any(i.strip() for i in ingredient_ids)

    # Delete existing recipe ingredients
    old_ingredients = await db.execute(
        select(RecipeIngredient).where(RecipeIngredient.recipe_id == food.id)
    )
    for ri in old_ingredients.scalars().all():
        await db.delete(ri)

    if has_ingredients:
        food.instrucciones = data.get("instrucciones", "") or None
        total_cal = total_pro = total_carbs = total_gras = 0
        total_weight = 0
        for iid, qty_str in zip(ingredient_ids, ingredient_qty):
            if not iid.strip():
                continue
            qty = float(qty_str or 0)
            if qty <= 0:
                continue
            ing = await db.get(FoodCatalog, int(iid))
            if not ing or ing.user_id != user.id:
                continue
            factor = qty / 100
            total_cal += (ing.calorias or 0) * factor
            total_pro += (ing.proteinas or 0) * factor
            total_carbs += (ing.carbs or 0) * factor
            total_gras += (ing.grasas or 0) * factor
            total_weight += qty
            db.add(RecipeIngredient(
                recipe_id=food.id, ingredient_id=ing.id, cantidad=qty,
            ))
        if total_weight > 0:
            food.calorias = round(total_cal / total_weight * 100, 1)
            food.proteinas = round(total_pro / total_weight * 100, 1)
            food.carbs = round(total_carbs / total_weight * 100, 1)
            food.grasas = round(total_gras / total_weight * 100, 1)
    else:
        food.instrucciones = None

    await db.commit()
    return RedirectResponse(url=f"/foods?search={quote(food.food_name)}", status_code=302)


@router.post("/{food_id}/set-group")
async def set_food_group(
    food_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    data = await request.form()
    result = await db.execute(
        select(FoodCatalog).where(
            FoodCatalog.id == food_id, FoodCatalog.user_id == user.id
        )
    )
    food = result.scalar_one_or_none()
    if not food:
        raise HTTPException(status_code=404)
    food.grupo = data.get("grupo", "") or None
    await db.commit()
    return RedirectResponse(url="/foods", status_code=302)


@router.post("/{food_id}/delete")
async def delete_food(
    food_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    result = await db.execute(
        select(FoodCatalog).where(
            FoodCatalog.id == food_id, FoodCatalog.user_id == user.id
        )
    )
    food = result.scalar_one_or_none()
    if not food:
        raise HTTPException(status_code=404)
    await db.delete(food)
    await db.commit()
    return RedirectResponse(url="/foods", status_code=302)
