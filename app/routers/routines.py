from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import Routine, RoutineExercise, Exercise, UserProfile
from app.auth import get_current_user

router = APIRouter(prefix="/routines", tags=["routines"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def list_routines(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(Routine)
        .where(Routine.user_id == user.id)
        .options(selectinload(Routine.exercises))
        .order_by(Routine.created_at.desc())
    )
    routines = result.scalars().all()
    return templates.TemplateResponse(request, "routines/list.html", {
        "user": user, "routines": routines
    })


@router.get("/exercises", response_class=HTMLResponse)
async def exercise_library(
    request: Request,
    grupo: str = Query(None),
    search: str = Query(""),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    query = select(Exercise)
    if grupo:
        query = query.where(Exercise.muscle_group == grupo)
    if search:
        query = query.where(
            Exercise.name.ilike(f"%{search}%") | Exercise.name_es.ilike(f"%{search}%")
        )
    query = query.order_by(Exercise.muscle_group, Exercise.name)
    result = await db.execute(query)
    exercises = result.scalars().all()

    grupos = ["Pecho", "Espalda", "Hombros", "Bíceps", "Tríceps", "Piernas", "Glúteos", "Abdomen", "Cardio"]

    return templates.TemplateResponse(request, "routines/exercises.html", {
        "user": user, "exercises": exercises,
        "grupos": grupos, "grupo": grupo, "search": search,
    })


@router.get("/new", response_class=HTMLResponse)
async def new_routine_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(Exercise).where(
            (Exercise.is_custom == False) | (Exercise.user_id == user.id)
        ).order_by(Exercise.muscle_group, Exercise.name)
    )
    exercises = result.scalars().all()

    muscle_groups = {}
    for ex in exercises:
        mg = ex.muscle_group or "Otros"
        if mg not in muscle_groups:
            muscle_groups[mg] = []
        muscle_groups[mg].append(ex)

    return templates.TemplateResponse(request, "routines/new.html", {
        "user": user, "muscle_groups": muscle_groups
    })


@router.post("/new")
async def create_routine(
    request: Request,
    nombre: str = Form(...),
    descripcion: str = Form(""),
    dia_semana: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    routine = Routine(
        user_id=user.id,
        nombre=nombre,
        descripcion=descripcion,
        dia_semana=dia_semana or None,
    )
    db.add(routine)
    await db.commit()
    await db.refresh(routine)
    return RedirectResponse(url=f"/routines/{routine.id}/edit", status_code=302)


@router.get("/{routine_id}", response_class=HTMLResponse)
async def view_routine(
    request: Request,
    routine_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(Routine)
        .where(Routine.id == routine_id, Routine.user_id == user.id)
        .options(selectinload(Routine.exercises).selectinload(RoutineExercise.exercise))
    )
    routine = result.scalar_one_or_none()
    if not routine:
        raise HTTPException(status_code=404, detail="Rutina no encontrada")

    return templates.TemplateResponse(request, "routines/view.html", {
        "user": user, "routine": routine
    })


@router.get("/{routine_id}/edit", response_class=HTMLResponse)
async def edit_routine_page(
    request: Request,
    routine_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(Routine)
        .where(Routine.id == routine_id, Routine.user_id == user.id)
        .options(selectinload(Routine.exercises))
    )
    routine = result.scalar_one_or_none()
    if not routine:
        raise HTTPException(status_code=404, detail="Rutina no encontrada")

    result = await db.execute(
        select(Exercise).where(
            (Exercise.is_custom == False) | (Exercise.user_id == user.id)
        ).order_by(Exercise.muscle_group, Exercise.name)
    )
    all_exercises = result.scalars().all()

    muscle_groups = {}
    for ex in all_exercises:
        mg = ex.muscle_group or "Otros"
        if mg not in muscle_groups:
            muscle_groups[mg] = []
        muscle_groups[mg].append(ex)

    return templates.TemplateResponse(request, "routines/edit.html", {
        "user": user, "routine": routine, "muscle_groups": muscle_groups
    })


@router.post("/{routine_id}/add-exercise")
async def add_exercise_to_routine(
    request: Request,
    routine_id: int,
    exercise_id: int = Form(...),
    sets: int = Form(3),
    min_reps: int = Form(8),
    max_reps: int = Form(12),
    peso: float = Form(0.0),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(Routine).where(Routine.id == routine_id, Routine.user_id == user.id)
    )
    routine = result.scalar_one_or_none()
    if not routine:
        raise HTTPException(status_code=404, detail="Rutina no encontrada")

    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    exercise = result.scalar_one_or_none()
    if not exercise:
        raise HTTPException(status_code=404, detail="Ejercicio no encontrado")

    result = await db.execute(
        select(RoutineExercise)
        .where(RoutineExercise.routine_id == routine_id)
        .order_by(RoutineExercise.orden.desc())
        .limit(1)
    )
    last_ex = result.scalar_one_or_none()
    next_order = (last_ex.orden + 1) if last_ex else 0

    re = RoutineExercise(
        routine_id=routine_id,
        exercise_id=exercise_id,
        exercise_name=exercise.name_es or exercise.name,
        sets=sets,
        min_reps=min_reps,
        max_reps=max_reps,
        peso=peso if peso > 0 else None,
        orden=next_order,
    )
    db.add(re)
    await db.commit()
    return RedirectResponse(url=f"/routines/{routine_id}/edit", status_code=302)


@router.post("/{routine_id}/remove-exercise/{exercise_id}")
async def remove_exercise_from_routine(
    routine_id: int,
    exercise_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    await db.execute(
        delete(RoutineExercise).where(
            RoutineExercise.id == exercise_id,
            RoutineExercise.routine_id == routine_id,
        )
    )
    await db.commit()
    return RedirectResponse(url=f"/routines/{routine_id}/edit", status_code=302)


@router.post("/{routine_id}/delete")
async def delete_routine(
    routine_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(Routine).where(Routine.id == routine_id, Routine.user_id == user.id)
    )
    routine = result.scalar_one_or_none()
    if routine:
        await db.delete(routine)
    await db.commit()
    return RedirectResponse(url="/routines", status_code=302)
