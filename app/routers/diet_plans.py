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

    return templates.TemplateResponse("diet_plans/list.html", {
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
    return templates.TemplateResponse("diet_plans/new.html", {
        "user": user, "meal_types": TIPOS_COMIDA
    })


TIPOS_COMIDA = ["Desayuno", "Almuerzo", "Comida", "Merienda", "Cena", "Snack", "Postre"]


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

    return templates.TemplateResponse("diet_plans/view.html", {
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

    return templates.TemplateResponse("diet_plans/edit.html", {
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
