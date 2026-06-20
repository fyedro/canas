from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import BodyMeasurement, UserProfile, Workout
from app.auth import get_current_user
from datetime import date

router = APIRouter(prefix="/progress", tags=["progress"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def progress_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    result = await db.execute(
        select(BodyMeasurement)
        .where(BodyMeasurement.user_id == user.id)
        .order_by(BodyMeasurement.fecha.desc())
        .limit(30)
    )
    measurements = result.scalars().all()

    return templates.TemplateResponse(request, "progress/index.html", {
        "user": user,
        "measurements": list(reversed(measurements)),
    })


@router.post("/measure")
async def add_measurement(
    request: Request,
    fecha: str = Form(""),
    peso: float = Form(None),
    grasa_corporal: float = Form(None),
    musculo: float = Form(None),
    agua: float = Form(None),
    hueso: float = Form(None),
    imc: float = Form(None),
    grasa_visceral: float = Form(None),
    metabolismo_basal: float = Form(None),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    today = date.fromisoformat(fecha) if fecha else date.today()

    result = await db.execute(
        select(BodyMeasurement).where(
            BodyMeasurement.user_id == user.id,
            BodyMeasurement.fecha == today,
        )
    )
    existing = result.scalar_one_or_none()

    fields = {
        "peso": peso, "grasa_corporal": grasa_corporal,
        "musculo": musculo, "agua": agua, "hueso": hueso,
        "imc": imc, "grasa_visceral": grasa_visceral,
        "metabolismo_basal": metabolismo_basal,
    }

    if existing:
        for k, v in fields.items():
            if v is not None:
                setattr(existing, k, v)
    else:
        bm = BodyMeasurement(user_id=user.id, fecha=today)
        for k, v in fields.items():
            if v is not None:
                setattr(bm, k, v)
        db.add(bm)

    await db.commit()
    return RedirectResponse(url="/progress", status_code=302)
