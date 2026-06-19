from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import UserProfile
from app.config import settings
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
import uuid

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def create_access_token(user_id: str, expires_delta: timedelta = None):
    to_encode = {"sub": user_id}
    if expires_delta:
        to_encode["exp"] = datetime.utcnow() + expires_delta
    else:
        to_encode["exp"] = datetime.utcnow() + timedelta(days=7)
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def verify_token(token: str):
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "auth/login.html")


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "auth/register.html")


@router.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    nombre: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserProfile).where(UserProfile.email == email))
    if result.scalar_one_or_none():
        return templates.TemplateResponse(request, "auth/register.html", {
            "error": "El email ya está registrado"
        })

    user = UserProfile(
        id=str(uuid.uuid4()),
        email=email,
        nombre=nombre,
        password_hash=pwd_context.hash(password),
    )
    db.add(user)
    await db.commit()

    token = create_access_token(user.id)
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(key="access_token", value=token, httponly=True, max_age=604800)
    return response


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserProfile).where(UserProfile.email == email))
    user = result.scalar_one_or_none()

    if not user or not pwd_context.verify(password, user.password_hash):
        return templates.TemplateResponse(request, "auth/login.html", {
            "error": "Email o contraseña incorrectos"
        })

    token = create_access_token(user.id)
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(key="access_token", value=token, httponly=True, max_age=604800)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=302)
    response.delete_cookie("access_token")
    return response


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        return None

    user_id = verify_token(token)
    if not user_id:
        return None

    result = await db.execute(select(UserProfile).where(UserProfile.id == user_id))
    return result.scalar_one_or_none()
