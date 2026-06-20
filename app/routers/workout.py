from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import Workout, WorkoutSet, Routine, RoutineExercise, UserProfile
from app.auth import get_current_user
from datetime import datetime, date

router = APIRouter(prefix="/workout", tags=["workout"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def workout_history(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(Workout)
        .where(Workout.user_id == user.id)
        .order_by(Workout.fecha.desc())
        .limit(20)
    )
    workouts = result.scalars().all()
    return templates.TemplateResponse(request, "workout/history.html", {
        "user": user, "workouts": workouts
    })


@router.get("/start/{routine_id}", response_class=HTMLResponse)
async def start_workout_page(
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

    workout = Workout(
        user_id=user.id,
        routine_id=routine_id,
        nombre=routine.nombre,
        fecha=date.today(),
        hora_inicio=datetime.utcnow(),
    )
    db.add(workout)
    await db.commit()
    await db.refresh(workout)

    return templates.TemplateResponse(request, "workout/active.html", {
        "user": user, "workout": workout, "routine": routine
    })


@router.get("/active/{workout_id}", response_class=HTMLResponse)
async def active_workout_page(
    request: Request,
    workout_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(Workout).where(Workout.id == workout_id, Workout.user_id == user.id)
    )
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Entrenamiento no encontrado")

    result = await db.execute(
        select(Routine).where(Routine.id == workout.routine_id)
        .options(selectinload(Routine.exercises).selectinload(RoutineExercise.exercise))
    )
    routine = result.scalar_one_or_none()
    if not routine:
        raise HTTPException(status_code=404, detail="Rutina no encontrada")

    return templates.TemplateResponse(request, "workout/active.html", {
        "user": user, "workout": workout, "routine": routine
    })


@router.post("/active/{workout_id}/save-set")
async def save_set(
    workout_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return {"error": "Not authenticated"}

    data = await request.json()
    ws = WorkoutSet(
        workout_id=workout_id,
        exercise_name=data["exercise_name"],
        exercise_order=data["exercise_order"],
        set_number=data["set_number"],
        weight=data.get("weight"),
        reps=data.get("reps"),
        completed=data.get("completed", True),
    )
    db.add(ws)
    await db.commit()
    return {"status": "ok"}


@router.post("/active/{workout_id}/delete-set/{set_id}")
async def delete_set(
    workout_id: int,
    set_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return {"error": "Not authenticated"}
    await db.execute(
        delete(WorkoutSet).where(
            WorkoutSet.id == set_id, WorkoutSet.workout_id == workout_id
        )
    )
    await db.commit()
    return {"status": "ok"}


@router.post("/active/{workout_id}/finish")
async def finish_workout(
    workout_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(Workout).where(Workout.id == workout_id, Workout.user_id == user.id)
    )
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="No encontrado")

    now = datetime.utcnow()
    workout.hora_fin = now
    if workout.hora_inicio:
        workout.duracion = int((now - workout.hora_inicio).total_seconds() / 60)

    await db.commit()
    return RedirectResponse(url=f"/workout/{workout_id}", status_code=302)


@router.get("/{workout_id}", response_class=HTMLResponse)
async def workout_detail(
    request: Request,
    workout_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(Workout)
        .where(Workout.id == workout_id, Workout.user_id == user.id)
        .options(selectinload(Workout.sets))
    )
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="No encontrado")

    exercises = {}
    total_volume = 0
    for s in workout.sets:
        if s.exercise_name not in exercises:
            exercises[s.exercise_name] = []
        exercises[s.exercise_name].append(s)
        if s.weight and s.reps:
            total_volume += s.weight * s.reps

    return templates.TemplateResponse(request, "workout/detail.html", {
        "user": user, "workout": workout,
        "exercises": exercises, "total_volume": total_volume
    })
