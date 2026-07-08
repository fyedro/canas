from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, text
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import Workout, WorkoutSet, Routine, RoutineExercise, RoutineSet, UserProfile, Exercise
from app.auth import get_current_user
from datetime import datetime, date

router = APIRouter(prefix="/workout", tags=["workout"])
templates = Jinja2Templates(directory="app/templates")



@router.get("/stats", response_class=HTMLResponse)
async def workout_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    # Monthly workout count for last 12 months
    from datetime import timedelta
    twelve_ago = date.today() - timedelta(days=365)
    result = await db.execute(
        text("""
            SELECT date_trunc('month', fecha) AS month,
                   COUNT(id) AS count,
                   COALESCE(SUM(duracion), 0) AS total_min
            FROM workouts
            WHERE user_id = :uid AND fecha >= :twelve_ago
            GROUP BY month
            ORDER BY month
        """), {"uid": user.id, "twelve_ago": twelve_ago}
    )
    monthly_rows = result.all()
    monthly_labels = []
    monthly_counts = []
    monthly_mins = []
    for row in monthly_rows:
        monthly_labels.append(row.month.strftime('%b %Y') if hasattr(row.month, 'strftime') else str(row.month))
        monthly_counts.append(row.count)
        monthly_mins.append(row.total_min)

    # Total weight per month
    result = await db.execute(
        text("""
            SELECT date_trunc('month', w.fecha) AS month,
                   COALESCE(SUM(ws.weight * ws.reps), 0) AS volume
            FROM workouts w
            JOIN workout_sets ws ON ws.workout_id = w.id
            WHERE w.user_id = :uid AND w.fecha >= :twelve_ago
              AND ws.completed = TRUE AND ws.weight IS NOT NULL AND ws.reps IS NOT NULL
            GROUP BY month
            ORDER BY month
        """), {"uid": user.id, "twelve_ago": twelve_ago}
    )
    volume_rows = result.all()
    month_set = set()
    vol_by_month = {}
    for row in volume_rows:
        key = row.month.strftime('%b %Y') if hasattr(row.month, 'strftime') else str(row.month)
        vol_by_month[key] = float(row.volume)
    volume_labels = []
    volume_data = []
    for ml in monthly_labels:
        volume_labels.append(ml)
        volume_data.append(round(vol_by_month.get(ml, 0), 1))

    # Most used exercises (top 10)
    result = await db.execute(
        select(
            WorkoutSet.exercise_name,
            func.count(WorkoutSet.id).label('total_sets'),
            func.avg(WorkoutSet.weight).label('avg_weight'),
            func.avg(WorkoutSet.reps).label('avg_reps'),
        )
        .select_from(WorkoutSet)
        .join(Workout)
        .where(
            Workout.user_id == user.id,
            WorkoutSet.completed == True,
        )
        .group_by(WorkoutSet.exercise_name)
        .order_by(func.count(WorkoutSet.id).desc())
        .limit(10)
    )
    top_exercises = result.all()

    # Muscle group distribution across ALL workouts
    result = await db.execute(
        select(Exercise).where(
            (Exercise.is_custom == False) | (Exercise.user_id == user.id)
        )
    )
    all_exercises = {e.name: e for e in result.scalars().all()}

    result = await db.execute(
        select(WorkoutSet.exercise_name, func.count(WorkoutSet.id).label('cnt'))
        .select_from(WorkoutSet)
        .join(Workout)
        .where(
            Workout.user_id == user.id,
            WorkoutSet.completed == True,
        )
        .group_by(WorkoutSet.exercise_name)
    )
    ex_counts = result.all()

    ALL_MUSCLES = [
        "Abdominales", "Antebrazo", "Bíceps", "Cardio", "Cuádriceps", "Cuello",
        "Cuerpo completo", "Dorsal", "Espalda baja", "Gemelos", "Glúteos",
        "Hombros", "Isquiotibiales", "Pecho", "Tríceps",
    ]
    muscle_total = {m: 0 for m in ALL_MUSCLES}
    for row in ex_counts:
        eo = all_exercises.get(row.exercise_name)
        if not eo:
            continue
        for m in ALL_MUSCLES:
            if m == eo.muscle_group:
                muscle_total[m] += row.cnt * 100
            elif m == eo.muscle_group_secondary:
                muscle_total[m] += row.cnt * 70
            elif m == eo.muscle_group_secondary2:
                muscle_total[m] += row.cnt * 40
    total_muscle = sum(muscle_total.values())
    if total_muscle:
        for m in muscle_total:
            muscle_total[m] = round(muscle_total[m] / total_muscle * 100, 1)

    # Filter out 0% groups
    muscle_present = {k: v for k, v in muscle_total.items() if v > 0}
    muscle_labels_stats = list(muscle_present.keys())
    muscle_values_stats = list(muscle_present.values())

    return templates.TemplateResponse(request, "workout/stats.html", {
        "user": user,
        "monthly_labels": monthly_labels,
        "monthly_counts": monthly_counts,
        "monthly_mins": monthly_mins,
        "volume_labels": volume_labels,
        "volume_data": volume_data,
        "top_exercises": top_exercises,
        "muscle_labels_stats": muscle_labels_stats,
        "muscle_values_stats": muscle_values_stats,
    })


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
        .options(
            selectinload(Routine.exercises).selectinload(RoutineExercise.exercise),
            selectinload(Routine.exercises).selectinload(RoutineExercise.sets),
        )
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
        .options(
            selectinload(Routine.exercises).selectinload(RoutineExercise.exercise),
            selectinload(Routine.exercises).selectinload(RoutineExercise.sets),
        )
    )
    routine = result.scalar_one_or_none()
    if not routine:
        raise HTTPException(status_code=404, detail="Rutina no encontrada")

    # All exercises for adding during workout
    result = await db.execute(
        select(Exercise).where(
            (Exercise.is_custom == False) | (Exercise.user_id == user.id)
        ).order_by(Exercise.name)
    )
    all_exercises = result.scalars().all()

    return templates.TemplateResponse(request, "workout/active.html", {
        "user": user, "workout": workout, "routine": routine,
        "all_exercises": all_exercises,
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


@router.post("/active/{workout_id}/update-set/{set_id}")
async def update_set(
    workout_id: int,
    set_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return {"error": "Not authenticated"}

    data = await request.json()
    ws = await db.get(WorkoutSet, set_id)
    if not ws or ws.workout_id != workout_id:
        return {"error": "Not found"}

    ws.weight = data.get("weight")
    ws.reps = data.get("reps")
    ws.completed = data.get("completed", ws.completed)
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
    request: Request,
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

    data = await request.form()
    total = data.get("total")
    if total:
        total = int(total)
        await db.execute(delete(WorkoutSet).where(WorkoutSet.workout_id == workout_id))

        # Update workout date if provided
    fecha_str = data.get("fecha")
    if fecha_str:
        try:
            workout.fecha = date.fromisoformat(fecha_str)
        except (ValueError, TypeError):
            pass

    total = int(data.get("total", 0))

    # Update workout date if provided
    fecha_str = data.get("fecha")
    if fecha_str:
        try:
            from datetime import date as date_type
            workout.fecha = date_type.fromisoformat(fecha_str)
        except (ValueError, TypeError):
            pass

    # Delete all existing sets and re-create from form data
    await db.execute(delete(WorkoutSet).where(WorkoutSet.workout_id == workout_id))

    for i in range(total):
        exercise_name = data.get(f"exercise_name_{i}")
        exercise_order = int(data.get(f"exercise_order_{i}", 0))
        set_number = int(data.get(f"set_number_{i}", 1))
        weight = data.get(f"weight_{i}")
        reps = data.get(f"reps_{i}")
        completed = data.get(f"completed_{i}", "false") == "true"
        is_timed = data.get(f"is_timed_{i}", "false") == "true"
        resistencia = data.get(f"resistencia_{i}")
        calorias = data.get(f"calorias_{i}")
        duracion_minutos = data.get(f"duracion_minutos_{i}")
        distancia_km = data.get(f"distancia_km_{i}")

        ws = WorkoutSet(
            workout_id=workout_id,
            exercise_name=exercise_name,
            exercise_order=exercise_order,
            set_number=set_number,
            weight=float(weight) if weight else None,
            reps=int(reps) if reps else None,
            is_timed=is_timed,
            completed=completed,
            resistencia=float(resistencia) if resistencia else None,
            calorias=float(calorias) if calorias else None,
            duracion_minutos=int(duracion_minutos) if duracion_minutos else None,
            distancia_km=float(distancia_km) if distancia_km else None,
        )
        db.add(ws)

    await db.commit()
    return RedirectResponse(url=f"/workout/{workout_id}", status_code=302)
