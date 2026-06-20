from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from app.config import settings
from app.database import engine
import os
import shutil

router = APIRouter(prefix="/api", tags=["api"])


@router.post("/upload-db")
async def upload_db(request: Request, file: UploadFile = File(...)):
    # Verify secret key
    secret = request.headers.get("X-Secret-Key")
    if secret != settings.secret_key:
        raise HTTPException(status_code=403, detail="Secret key inválida")

    if not file.filename.endswith(".db"):
        raise HTTPException(status_code=400, detail="Solo archivos .db")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    db_path = "canas.db"

    # Backup old DB if exists
    if os.path.exists(db_path):
        shutil.copy2(db_path, db_path + ".backup")

    # Write new DB
    with open(db_path, "wb") as f:
        f.write(content)

    # Dispose old engine connections so next requests use the new DB
    await engine.dispose()

    return JSONResponse({
        "status": "ok",
        "message": f"Base de datos actualizada ({len(content)} bytes)",
        "size": len(content),
    })
