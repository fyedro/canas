from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import FoodCatalog, RecipeIngredient, UserProfile, FOOD_GROUPS
from app.auth import get_current_user
from urllib.parse import quote

router = APIRouter(prefix="/recipes", tags=["recipes"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def list_recipes(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(FoodCatalog).where(
            FoodCatalog.user_id == user.id,
            FoodCatalog.recipe_ingredients.any(),
        ).order_by(FoodCatalog.food_name)
    )
    recipes = result.scalars().all()

    return templates.TemplateResponse(request, "recipes/list.html", {
        "user": user, "recipes": recipes,
    })


@router.get("/new", response_class=HTMLResponse)
async def new_recipe_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    catalog = (await db.execute(
        select(FoodCatalog).where(FoodCatalog.user_id == user.id)
        .order_by(FoodCatalog.food_name)
    )).scalars().all()
    return templates.TemplateResponse(request, "recipes/new.html", {
        "user": user, "catalog": catalog, "food_groups": FOOD_GROUPS,
    })


@router.post("/new")
async def create_recipe(
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
        calorias=0, proteinas=0, carbs=0, grasas=0,
        instrucciones=data.get("instrucciones", "") or None,
    )
    db.add(food)
    await db.flush()

    ingredient_ids = data.getlist("ingredient_id")
    ingredient_qty = data.getlist("ingredient_qty")
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

    await db.commit()
    return RedirectResponse(url=f"/recipes/{food.id}", status_code=302)


@router.get("/{recipe_id}", response_class=HTMLResponse)
async def recipe_detail(
    request: Request,
    recipe_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(FoodCatalog).where(
            FoodCatalog.id == recipe_id,
            FoodCatalog.user_id == user.id,
        ).options(selectinload(FoodCatalog.recipe_ingredients).selectinload(RecipeIngredient.ingredient))
    )
    recipe = result.scalar_one_or_none()
    if not recipe or not recipe.recipe_ingredients:
        raise HTTPException(status_code=404)

    total_weight = sum(ri.cantidad for ri in recipe.recipe_ingredients)

    return templates.TemplateResponse(request, "recipes/detail.html", {
        "user": user, "recipe": recipe, "total_weight": total_weight,
    })
