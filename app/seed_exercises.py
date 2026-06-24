import asyncio
import json
import httpx
from sqlalchemy import select
from app.database import async_session, init_db
from app.models import Exercise

MUSCLE_MAP = {
    "chest": "Pecho", "triceps": "Tríceps", "shoulders": "Hombros",
    "back": "Espalda", "biceps": "Bíceps", "legs": "Piernas",
    "glutes": "Glúteos", "abs": "Abdomen", "cardio": "Cardio",
    "full body": "Cuerpo completo", "calves": "Piernas",
    "abductors": "Piernas", "adductors": "Piernas", "neck": "Cuello",
    "forearms": "Bíceps", "trapezius": "Espalda", "lats": "Espalda",
}


def parse_wger(wger_ex):
    wid = wger_ex["id"]
    name = ""
    description = ""
    for t in wger_ex.get("translations", []):
        if t.get("language") == 4:
            name = t["name"]
            description = t.get("description", "") or ""
            break
    if not name and wger_ex.get("translations"):
        t0 = wger_ex["translations"][0]
        name = t0["name"]
        description = t0.get("description", "") or ""

    cat_name = wger_ex["category"]["name"] if wger_ex.get("category") else ""
    muscle = MUSCLE_MAP.get(cat_name.lower().strip(), cat_name)
    img = wger_ex["images"][0]["image"] if wger_ex.get("images") else None

    muscles_list = [m["name"] for m in wger_ex.get("muscles", [])]
    sec_muscles = [m["name"] for m in wger_ex.get("muscles_secondary", [])]
    target_muscles = json.dumps({"primary": muscles_list, "secondary": sec_muscles})

    equipment_list = [e["name"] for e in wger_ex.get("equipment", [])]
    equipment = ", ".join(equipment_list) if equipment_list else None

    return wid, name, description, muscle, img, target_muscles, equipment


async def seed_database():
    await init_db()

    async with async_session() as session:
        result = await session.execute(select(Exercise).limit(1))
        if result.scalar_one_or_none():
            print("Ejercicios ya existen. Sincronizando datos desde wger...")
            await sync_from_wger()
            return

        print("Descargando ejercicios desde wger API...")
        added = 0
        url = "https://wger.de/api/v2/exerciseinfo/?language=4&limit=200"
        async with httpx.AsyncClient() as client:
            while url and added < 1000:
                try:
                    resp = await client.get(url, timeout=15)
                    data = resp.json()
                except Exception as e:
                    print(f"Error fetching wger: {e}")
                    break

                for wger_ex in data.get("results", []):
                    wid, name, description, muscle, img, target_muscles, equipment = parse_wger(wger_ex)
                    if not name:
                        continue

                    existing = await session.execute(
                        select(Exercise).where(Exercise.wger_id == wid)
                    )
                    if existing.scalar_one_or_none():
                        continue

                    session.add(Exercise(
                        name=name,
                        name_es=name,
                        muscle_group=muscle,
                        description=description,
                        target_muscles=target_muscles,
                        equipment=equipment,
                        image_url=img,
                        wger_id=wid,
                    ))
                    added += 1

                url = data.get("next")

        await session.commit()
        print(f"✅ {added} ejercicios guardados con datos de wger")


async def sync_from_wger():
    """Sync existing exercises with wger data: update descriptions, muscles, images."""
    async with httpx.AsyncClient() as client:
        wger_exercises = []
        url = "https://wger.de/api/v2/exerciseinfo/?language=4&limit=200"
        while url:
            try:
                resp = await client.get(url, timeout=15)
                data = resp.json()
                wger_exercises.extend(data.get("results", []))
                url = data.get("next")
            except Exception as e:
                print(f"Error fetching wger: {e}")
                break

        async with async_session() as session:
            all_existing = (await session.execute(select(Exercise))).scalars().all()
            by_name = {}
            by_wger = {}
            for ex in all_existing:
                by_name[ex.name.lower()] = ex
                if ex.wger_id:
                    by_wger[ex.wger_id] = ex

            updated = 0
            added = 0
            new_objs = []

            for wger_ex in wger_exercises:
                wid, name, description, muscle, img, target_muscles, equipment = parse_wger(wger_ex)
                if not name:
                    continue

                changed = False

                if wid in by_wger:
                    ex = by_wger[wid]
                    if not ex.description and description:
                        ex.description = description; changed = True
                    if not ex.target_muscles and target_muscles:
                        ex.target_muscles = target_muscles; changed = True
                    if not ex.equipment and equipment:
                        ex.equipment = equipment; changed = True
                    if img and not ex.image_url:
                        ex.image_url = img; changed = True
                    if changed:
                        updated += 1
                    continue

                key = name.lower()
                if key in by_name:
                    ex = by_name[key]
                    if not ex.description and description:
                        ex.description = description; changed = True
                    if not ex.target_muscles and target_muscles:
                        ex.target_muscles = target_muscles; changed = True
                    if not ex.equipment and equipment:
                        ex.equipment = equipment; changed = True
                    if img and not ex.image_url:
                        ex.image_url = img; changed = True
                    if not ex.wger_id:
                        ex.wger_id = wid; changed = True
                    if not ex.muscle_group and muscle:
                        ex.muscle_group = muscle; changed = True
                    if changed:
                        updated += 1
                    continue

                new_objs.append(Exercise(
                    name=name,
                    name_es=name,
                    muscle_group=muscle,
                    description=description,
                    target_muscles=target_muscles,
                    equipment=equipment,
                    image_url=img,
                    wger_id=wid,
                ))
                added += 1

            for obj in new_objs:
                session.add(obj)

            await session.commit()
            print(f"✅ {updated} ejercicios actualizados, {added} ejercicios nuevos")


if __name__ == "__main__":
    asyncio.run(seed_database())
