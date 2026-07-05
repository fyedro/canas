import json
import os
import uuid
from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import Routine, RoutineExercise, RoutineSet, Exercise, WorkoutSet, UserProfile
from app.auth import get_current_user

router = APIRouter(prefix="/routines", tags=["routines"])
templates = Jinja2Templates(directory="app/templates")


def _is_video(url):
    if not url:
        return False
    return any(url.lower().endswith(ext) for ext in (".mp4", ".webm", ".mov", ".avi", ".mkv"))


templates.env.filters["is_video"] = _is_video


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

    usage_subq = (
        select(func.count(WorkoutSet.id))
        .where(WorkoutSet.exercise_name == Exercise.name)
        .correlate(Exercise)
        .scalar_subquery()
    )
    query = select(Exercise, usage_subq.label("usage_count"))
    if grupo:
        query = query.where(Exercise.muscle_group == grupo)
    if search:
        query = query.where(
            Exercise.name.ilike(f"%{search}%") | Exercise.name_es.ilike(f"%{search}%")
        )
    query = query.order_by(
        usage_subq.desc(),
        Exercise.muscle_group,
        Exercise.name,
    )
    result = await db.execute(query)
    rows = result.all()
    exercises = [ex for ex, _ in rows]
    usage_counts = {ex.id: cnt for ex, cnt in rows}

    grupo_rows = (await db.execute(select(Exercise.muscle_group).distinct())).scalars().all()
    grupos = sorted(set(g for g in grupo_rows if g)) or [
        "Abdominales", "Antebrazo", "Bíceps", "Cardio", "Cuádriceps", "Cuello",
        "Cuerpo completo", "Dorsal", "Espalda baja", "Gemelos", "Glúteos",
        "Hombros", "Isquiotibiales", "Pecho", "Tríceps",
    ]

    return templates.TemplateResponse(request, "routines/exercises.html", {
        "user": user, "exercises": exercises,
        "grupos": grupos, "grupo": grupo, "search": search,
        "usage_counts": usage_counts,
    })


MUSCLE_GROUP_OPTIONS = sorted([
    "Abdominales", "Antebrazo", "Bíceps", "Cardio", "Cuádriceps", "Cuello",
    "Cuerpo completo", "Dorsal", "Espalda baja", "Gemelos", "Glúteos",
    "Hombros", "Isquiotibiales", "Pecho", "Tríceps",
])

EQUIPMENT_OPTIONS = sorted(["Banco", "Barra", "Banda de resistencia", "Cajón", "Kettlebell", "Mancuerna", "Máquina", "Rueda", "Suspensión"])


@router.get("/exercises/new", response_class=HTMLResponse)
async def new_exercise_page(
    request: Request,
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    return templates.TemplateResponse(request, "routines/exercise_form.html", {
        "user": user, "grupos": MUSCLE_GROUP_OPTIONS, "exercise": None,
        "equipment_options": EQUIPMENT_OPTIONS,
    })


@router.post("/exercises/new")
async def create_exercise(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
    image_file: UploadFile = File(None),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    data = await request.form()

    name = data["name"].strip()
    if not name:
        return templates.TemplateResponse(request, "routines/exercise_form.html", {
            "user": user, "grupos": MUSCLE_GROUP_OPTIONS, "exercise": None,
            "equipment_options": EQUIPMENT_OPTIONS,
            "error": "El nombre no puede estar vacío",
        }, status_code=400)

    existing = await db.execute(select(Exercise).where(Exercise.name == name))
    if existing.scalar_one_or_none():
        return templates.TemplateResponse(request, "routines/exercise_form.html", {
            "user": user, "grupos": MUSCLE_GROUP_OPTIONS, "exercise": None,
            "equipment_options": EQUIPMENT_OPTIONS,
            "error": f"Ya existe un ejercicio llamado «{name}»",
        }, status_code=400)

    image_url = data.get("image_url", "") or None
    if image_file and image_file.filename:
        ext = os.path.splitext(image_file.filename)[1] or ".jpg"
        filename = f"{uuid.uuid4().hex}{ext}"
        dest = f"app/static/uploads/exercises/{filename}"
        with open(dest, "wb") as f:
            f.write(await image_file.read())
        image_url = f"/static/uploads/exercises/{filename}"

    ex = Exercise(
        name=data["name"],
        name_es=data.get("name", ""),
        muscle_group=data.get("muscle_group", "") or None,
        muscle_group_secondary=data.get("muscle_group_secondary", "") or None,
        muscle_group_secondary2=data.get("muscle_group_secondary2", "") or None,
        equipment=", ".join(data.getlist("equipment")) or None,
        is_timed=data.get("is_timed") == "1",
        show_cardio_metrics=data.get("show_cardio_metrics") == "1",
        image_url=image_url,
        is_custom=True,
        user_id=user.id,
    )
    db.add(ex)
    await db.commit()
    return RedirectResponse(url="/routines/exercises", status_code=302)


@router.get("/exercises/{exercise_id}", response_class=HTMLResponse)
async def exercise_detail(
    request: Request,
    exercise_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(Exercise).where(Exercise.id == exercise_id)
    )
    exercise = result.scalar_one_or_none()
    if not exercise:
        raise HTTPException(status_code=404, detail="Ejercicio no encontrado")

    target_muscles = []
    if exercise.target_muscles:
        try:
            parsed = json.loads(exercise.target_muscles)
            target_muscles = parsed.get("primary", []) + parsed.get("secondary", [])
        except (json.JSONDecodeError, TypeError):
            pass

    ALL_MUSCLES = [
        "Abdominales", "Antebrazo", "Bíceps", "Cardio", "Cuádriceps", "Cuello",
        "Cuerpo completo", "Dorsal", "Espalda baja", "Gemelos", "Glúteos",
        "Hombros", "Isquiotibiales", "Pecho", "Tríceps",
    ]
    muscle_radar = {}
    for m in ALL_MUSCLES:
        if m == exercise.muscle_group:
            muscle_radar[m] = 100
        elif m == exercise.muscle_group_secondary:
            muscle_radar[m] = 70
        elif m == exercise.muscle_group_secondary2:
            muscle_radar[m] = 40
        else:
            muscle_radar[m] = 0

    return templates.TemplateResponse(request, "routines/exercise_detail.html", {
        "user": user,
        "exercise": exercise,
        "target_muscles": target_muscles,
        "muscle_labels": list(muscle_radar.keys()),
        "muscle_values": list(muscle_radar.values()),
    })


@router.get("/exercises/{exercise_id}/edit", response_class=HTMLResponse)
async def edit_exercise_page(
    request: Request,
    exercise_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    exercise = await db.get(Exercise, exercise_id)
    if not exercise:
        return HTMLResponse("Ejercicio no encontrado", status_code=404)
    return templates.TemplateResponse(request, "routines/exercise_form.html", {
        "user": user, "grupos": MUSCLE_GROUP_OPTIONS, "exercise": exercise,
        "equipment_options": EQUIPMENT_OPTIONS,
    })


@router.post("/exercises/{exercise_id}/edit")
async def update_exercise(
    request: Request,
    exercise_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
    image_file: UploadFile = File(None),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    exercise = await db.get(Exercise, exercise_id)
    if not exercise:
        return HTMLResponse("Ejercicio no encontrado", status_code=404)
    data = await request.form()

    name = data["name"].strip()
    if not name:
        return templates.TemplateResponse(request, "routines/exercise_form.html", {
            "user": user, "grupos": MUSCLE_GROUP_OPTIONS, "exercise": exercise,
            "equipment_options": EQUIPMENT_OPTIONS,
            "error": "El nombre no puede estar vacío",
        }, status_code=400)

    existing = await db.execute(
        select(Exercise).where(Exercise.name == name, Exercise.id != exercise_id)
    )
    if existing.scalar_one_or_none():
        return templates.TemplateResponse(request, "routines/exercise_form.html", {
            "user": user, "grupos": MUSCLE_GROUP_OPTIONS, "exercise": exercise,
            "equipment_options": EQUIPMENT_OPTIONS,
            "error": f"Ya existe un ejercicio llamado «{name}»",
        }, status_code=400)

    exercise.name = name
    exercise.name_es = data.get("name", "")
    exercise.muscle_group = data.get("muscle_group", "") or None
    exercise.muscle_group_secondary = data.get("muscle_group_secondary", "") or None
    exercise.muscle_group_secondary2 = data.get("muscle_group_secondary2", "") or None
    exercise.equipment = ", ".join(data.getlist("equipment")) or None
    exercise.is_timed = data.get("is_timed") == "1"
    exercise.show_cardio_metrics = data.get("show_cardio_metrics") == "1"

    image_url = data.get("image_url", "") or None
    if image_file and image_file.filename:
        ext = os.path.splitext(image_file.filename)[1] or ".jpg"
        filename = f"{uuid.uuid4().hex}{ext}"
        dest = f"app/static/uploads/exercises/{filename}"
        with open(dest, "wb") as f:
            f.write(await image_file.read())
        exercise.image_url = f"/static/uploads/exercises/{filename}"
    elif image_url:
        exercise.image_url = image_url

    await db.commit()
    return RedirectResponse(url=f"/routines/exercises/{exercise_id}", status_code=302)


@router.post("/exercises/{exercise_id}/delete")
async def delete_exercise(
    exercise_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    exercise = await db.get(Exercise, exercise_id)
    if not exercise:
        return HTMLResponse("Ejercicio no encontrado", status_code=404)
    await db.execute(delete(RoutineExercise).where(RoutineExercise.exercise_id == exercise_id))
    await db.delete(exercise)
    await db.commit()
    return RedirectResponse(url="/routines/exercises", status_code=302)


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
        .options(
            selectinload(Routine.exercises).selectinload(RoutineExercise.exercise),
            selectinload(Routine.exercises).selectinload(RoutineExercise.sets),
        )
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
        .options(
            selectinload(Routine.exercises).selectinload(RoutineExercise.sets),
            selectinload(Routine.exercises).selectinload(RoutineExercise.exercise),
        )
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


@router.post("/{routine_id}/edit")
async def update_routine(
    routine_id: int,
    request: Request,
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
    data = await request.form()
    routine.nombre = data.get("nombre", routine.nombre)
    routine.vueltas = int(data.get("vueltas", 1))
    rest_v = data.get("rest_entre_vueltas")
    routine.rest_entre_vueltas = int(rest_v) if rest_v else None
    await db.commit()
    return RedirectResponse(url=f"/routines/{routine_id}/edit", status_code=302)


@router.post("/{routine_id}/add-exercise")
async def add_exercise_to_routine(
    request: Request,
    routine_id: int,
    exercise_id: int = Form(...),
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
        orden=next_order,
    )
    db.add(re)
    await db.commit()
    await db.refresh(re)

    rs = RoutineSet(
        routine_exercise_id=re.id,
        set_number=1,
        weight=None,
        reps=None,
    )
    db.add(rs)
    await db.commit()

    return RedirectResponse(url=f"/routines/{routine_id}/edit", status_code=302)


@router.post("/{routine_id}/exercises/{re_id}/add-set")
async def add_set_to_exercise(
    routine_id: int,
    re_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return {"error": "Not authenticated"}

    result = await db.execute(
        select(RoutineExercise).where(
            RoutineExercise.id == re_id,
            RoutineExercise.routine_id == routine_id,
        )
    )
    re = result.scalar_one_or_none()
    if not re:
        raise HTTPException(status_code=404, detail="Ejercicio no encontrado en la rutina")

    result = await db.execute(
        select(RoutineSet)
        .where(RoutineSet.routine_exercise_id == re_id)
        .order_by(RoutineSet.set_number.desc())
        .limit(1)
    )
    last_set = result.scalar_one_or_none()
    next_set_number = (last_set.set_number + 1) if last_set else 1

    rs = RoutineSet(
        routine_exercise_id=re_id,
        set_number=next_set_number,
        weight=last_set.weight if last_set else None,
        reps=last_set.reps if last_set else None,
    )
    db.add(rs)
    await db.commit()
    return RedirectResponse(url=f"/routines/{routine_id}/edit", status_code=302)


@router.post("/{routine_id}/exercises/{re_id}/update-set/{set_id}")
async def update_set(
    routine_id: int,
    re_id: int,
    set_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return {"error": "Not authenticated"}

    data = await request.form()
    rs = await db.get(RoutineSet, set_id)
    if not rs or rs.routine_exercise_id != re_id:
        raise HTTPException(status_code=404, detail="Serie no encontrada")

    rs.weight = float(data.get("weight")) if data.get("weight") else None
    rs.reps = int(data.get("reps")) if data.get("reps") else None
    await db.commit()
    return RedirectResponse(url=f"/routines/{routine_id}/edit", status_code=302)


@router.post("/{routine_id}/exercises/{re_id}/remove-set/{set_id}")
async def remove_set_from_exercise(
    routine_id: int,
    re_id: int,
    set_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return {"error": "Not authenticated"}

    await db.execute(
        delete(RoutineSet).where(
            RoutineSet.id == set_id,
            RoutineSet.routine_exercise_id == re_id,
        )
    )
    await db.commit()
    return RedirectResponse(url=f"/routines/{routine_id}/edit", status_code=302)


@router.post("/{routine_id}/exercises/{re_id}/update-rest")
async def update_exercise_rest(
    routine_id: int,
    re_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")
    re = await db.get(RoutineExercise, re_id)
    if not re or re.routine_id != routine_id:
        raise HTTPException(status_code=404, detail="Ejercicio no encontrado")
    data = await request.form()
    rest = data.get("rest_time")
    re.rest_time = int(rest) if rest else None
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
