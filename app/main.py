from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db, init_db, async_session
from app.auth import router as auth_router, get_current_user
from app.routers import routines, diet, progress, workout, diet_plans, foods, recipes
from app.config import settings
from app.models import Exercise
templates = Jinja2Templates(directory="app/templates")


def is_video(url):
    if not url:
        return False
    return any(url.lower().endswith(ext) for ext in (".mp4", ".webm", ".mov", ".avi", ".mkv"))


templates.env.filters["is_video"] = is_video


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(auth_router)
app.include_router(routines.router)
app.include_router(diet.router)
app.include_router(progress.router)
app.include_router(workout.router)
app.include_router(diet_plans.router)
app.include_router(foods.router)
app.include_router(recipes.router)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url="/auth/login")

    from sqlalchemy import select
    from app.models import Workout, BodyMeasurement
    from datetime import date

    today = date.today()
    result = await db.execute(
        select(Workout).where(Workout.user_id == user.id, Workout.fecha == today)
    )
    today_workout = result.scalar_one_or_none()

    result = await db.execute(
        select(BodyMeasurement).where(BodyMeasurement.user_id == user.id)
        .order_by(BodyMeasurement.fecha.desc()).limit(7)
    )
    recent_weight = result.scalars().all()

    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user,
        "today_workout": today_workout,
        "recent_weight": recent_weight,
    })
