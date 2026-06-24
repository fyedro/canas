import io
import re
from fastapi import APIRouter, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import BodyMeasurement, UserProfile, Workout
from app.auth import get_current_user
from datetime import date
from PIL import Image

try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = "/opt/homebrew/bin/tesseract"
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

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


@router.post("/ocr")
async def ocr_scale_image(
    file: UploadFile = File(...),
    user: UserProfile = Depends(get_current_user),
):
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    if not OCR_AVAILABLE:
        return JSONResponse({"error": "OCR no disponible en el servidor"}, status_code=501)

    contents = await file.read()
    img = Image.open(io.BytesIO(contents))
    img = img.convert("L")
    text = pytesseract.image_to_string(img, lang="spa+eng")
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]

    # Try to parse common patterns from Xiaomi Mi Body Scale / Fitdays output
    values = {}

    # Line "104.9 kg 32.7 32.0 %" → peso, imc, grasa_corporal
    for l in lines:
        nums = re.findall(r"(\d+[.,]\d+)", l)
        has_kg = "kg" in l.lower() or "Kg" in l
        has_pct = "%" in l
        if has_kg and has_pct and len(nums) >= 3:
            v = float(nums[0].replace(",", "."))
            if 20 < v < 300: values["peso"] = v
            v = float(nums[1].replace(",", "."))
            if 10 < v < 50: values["imc"] = v
            v = float(nums[2].replace(",", "."))
            if 1 < v < 70: values["grasa_corporal"] = v

    # Líneas con etiqueta + valor
    patterns = [
        # Peso: "104.9kg Sobrepeso" or "Peso 104.9 kg"
        ("peso", r"(?i)(?:peso|weight)\s*[:\s]*(\d+[.,]\d+)", lambda v: 20 < v < 300),
        ("peso", r"(\d+[.,]\d+)\s*kg(?!\s*\d)", lambda v: 20 < v < 300),

        # IMC: "32.7 alto" or "IMC 32.7"
        ("imc", r"(?i)(?:imc|bmi)\s*[:\s]*(\d+[.,]\d+)", lambda v: 10 < v < 50),

        # Grasa corporal: "Grasa Corporal 32.0%"
        ("grasa_corporal", r"(?i)grasa\s+corporal\s*[:\s]*(\d+[.,]\d+)", lambda v: 1 < v < 70),
        ("grasa_corporal", r"(?i)grasa\s+corporal\s+(\d+[.,]\d+)\s*%", lambda v: 1 < v < 70),

        # Agua corporal: "Agua Corporal 49.1%"
        ("agua", r"(?i)agua\s+corporal\s*[:\s]*(\d+[.,]\d+)", lambda v: 10 < v < 90),

        # Músculo: prefer "Musculo esquelético X%" over "Frecuencia muscular X%"
        ("musculo", r"(?i)musculo\s+esquel[eé]tico\s*[:\s]*(\d+[.,]\d+)", lambda v: 5 < v < 80),
        ("musculo", r"(?i)frecuencia\s+muscular\s*[:\s]*(\d+[.,]\d+)", lambda v: 5 < v < 80),
        ("musculo", r"(?i)(?:musculo|músculo|muscle)\s+[a-záéíóú]+\s*(\d+[.,]\d+)", lambda v: 5 < v < 80),

        # Hueso: "Masa Esquelética 3.6kg"
        ("hueso", r"(?i)masa\s+esquelética\s*[:\s]*(\d+[.,]\d+)", lambda v: 0.5 < v < 10),

        # Grasa visceral: "Grasa Visceral 15"
        ("grasa_visceral", r"(?i)grasa\s+visceral\s*[:\s]*(\d+[.,:]\d*)", lambda v: 1 < v < 30),

        # Grasa subcutánea: "Grasa subcutanea 27.6%"
        ("grasa_subcutanea", r"(?i)grasa\s+subcutanea\s*[:\s]*(\d+[.,]\d+)", lambda v: 1 < v < 70),

        # Proteína: "Proteina 15.5%"
        ("proteina", r"(?i)proteina\s*[:\s]*(\d+[.,]\d+)", lambda v: 1 < v < 50),

        # Masa muscular en kg: "Masa Muscular 67.7kg"
        ("masa_muscular_kg", r"(?i)masa\s+muscular\s*[:\s]*(\d+[.,]\d+)", lambda v: 10 < v < 200),

        # Edad corporal: "Edad Corporal 56"
        ("edad_corporal", r"(?i)edad\s+corporal\s*[:\s]*(\d+)", lambda v: 10 < v < 100),

        # Metabolismo basal: "1909kcal Bajo"
        ("metabolismo_basal", r"(\d+)\s*kcal", lambda v: 500 < v < 5000),
        ("metabolismo_basal", r"(?i)(?:bmr|metabolismo|basal|tmb|rmr)\s*[:\s]*(\d+)", lambda v: 500 < v < 5000),
    ]

    for field, pattern, validator in patterns:
        if field in values:
            continue
        for l in lines:
            m = re.search(pattern, l)
            if m:
                raw = m.group(1).replace(",", ".").replace(":", ".")
                try:
                    v = float(raw)
                except ValueError:
                    continue
                if validator(v):
                    values[field] = v
                    break

    return JSONResponse({"text": text, "lines": lines, "values": values})


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
    grasa_subcutanea: float = Form(None),
    proteina: float = Form(None),
    masa_muscular_kg: float = Form(None),
    edad_corporal: float = Form(None),
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
        "grasa_subcutanea": grasa_subcutanea,
        "proteina": proteina,
        "masa_muscular_kg": masa_muscular_kg,
        "edad_corporal": edad_corporal,
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
