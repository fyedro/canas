"""
Seed exercises from wger API (free, open-source exercise database with images).
"""
import asyncio
import httpx
from sqlalchemy import select
from app.database import async_session, init_db
from app.models import Exercise


EXERCISE_FALLBACKS = [
    {"name": "Press banca con barra", "name_es": "Press banca con barra", "muscle_group": "Pecho", "category": "Fuerza"},
    {"name": "Press banca inclinado con mancuernas", "name_es": "Press banca inclinado con mancuernas", "muscle_group": "Pecho", "category": "Fuerza"},
    {"name": "Aperturas con mancuernas", "name_es": "Aperturas con mancuernas", "muscle_group": "Pecho", "category": "Aislamiento"},
    {"name": "Flexiones", "name_es": "Flexiones", "muscle_group": "Pecho", "category": "Calistenia"},
    {"name": "Fondos en paralelas", "name_es": "Fondos en paralelas", "muscle_group": "Pecho", "category": "Calistenia"},
    {"name": "Press militar con barra", "name_es": "Press militar con barra", "muscle_group": "Hombros", "category": "Fuerza"},
    {"name": "Elevaciones laterales con mancuernas", "name_es": "Elevaciones laterales con mancuernas", "muscle_group": "Hombros", "category": "Aislamiento"},
    {"name": "Elevaciones frontales con mancuernas", "name_es": "Elevaciones frontales con mancuernas", "muscle_group": "Hombros", "category": "Aislamiento"},
    {"name": "Pájaros con mancuernas", "name_es": "Pájaros con mancuernas", "muscle_group": "Hombros", "category": "Aislamiento"},
    {"name": "Dominadas", "name_es": "Dominadas", "muscle_group": "Espalda", "category": "Calistenia"},
    {"name": "Remo con barra", "name_es": "Remo con barra", "muscle_group": "Espalda", "category": "Fuerza"},
    {"name": "Remo con mancuerna a una mano", "name_es": "Remo con mancuerna a una mano", "muscle_group": "Espalda", "category": "Fuerza"},
    {"name": "Jalón al pecho", "name_es": "Jalón al pecho", "muscle_group": "Espalda", "category": "Fuerza"},
    {"name": "Peso muerto", "name_es": "Peso muerto", "muscle_group": "Espalda", "category": "Fuerza"},
    {"name": "Curl con barra", "name_es": "Curl con barra", "muscle_group": "Bíceps", "category": "Aislamiento"},
    {"name": "Curl con mancuernas alterno", "name_es": "Curl con mancuernas alterno", "muscle_group": "Bíceps", "category": "Aislamiento"},
    {"name": "Curl martillo", "name_es": "Curl martillo", "muscle_group": "Bíceps", "category": "Aislamiento"},
    {"name": "Curl predicador", "name_es": "Curl predicador", "muscle_group": "Bíceps", "category": "Aislamiento"},
    {"name": "Extensiones de tríceps con cuerda", "name_es": "Extensiones de tríceps con cuerda", "muscle_group": "Tríceps", "category": "Aislamiento"},
    {"name": "Press francés con barra Z", "name_es": "Press francés con barra Z", "muscle_group": "Tríceps", "category": "Aislamiento"},
    {"name": "Fondos en banco para tríceps", "name_es": "Fondos en banco para tríceps", "muscle_group": "Tríceps", "category": "Calistenia"},
    {"name": "Patada de tríceps con mancuerna", "name_es": "Patada de tríceps con mancuerna", "muscle_group": "Tríceps", "category": "Aislamiento"},
    {"name": "Sentadilla con barra", "name_es": "Sentadilla con barra", "muscle_group": "Piernas", "category": "Fuerza"},
    {"name": "Prensa de piernas", "name_es": "Prensa de piernas", "muscle_group": "Piernas", "category": "Fuerza"},
    {"name": "Extensiones de piernas", "name_es": "Extensiones de piernas", "muscle_group": "Piernas", "category": "Aislamiento"},
    {"name": "Curl femoral tumbado", "name_es": "Curl femoral tumbado", "muscle_group": "Piernas", "category": "Aislamiento"},
    {"name": "Peso muerto rumano", "name_es": "Peso muerto rumano", "muscle_group": "Piernas", "category": "Fuerza"},
    {"name": "Zancadas con mancuernas", "name_es": "Zancadas con mancuernas", "muscle_group": "Piernas", "category": "Fuerza"},
    {"name": "Elevación de talones de pie", "name_es": "Elevación de talones de pie", "muscle_group": "Piernas", "category": "Aislamiento"},
    {"name": "Hip thrust", "name_es": "Hip thrust", "muscle_group": "Glúteos", "category": "Fuerza"},
    {"name": "Patada de glúteo en polea", "name_es": "Patada de glúteo en polea", "muscle_group": "Glúteos", "category": "Aislamiento"},
    {"name": "Abducción de cadera en máquina", "name_es": "Abducción de cadera en máquina", "muscle_group": "Glúteos", "category": "Aislamiento"},
    {"name": "Plancha", "name_es": "Plancha", "muscle_group": "Abdomen", "category": "Calistenia"},
    {"name": "Crunch abdominal", "name_es": "Crunch abdominal", "muscle_group": "Abdomen", "category": "Aislamiento"},
    {"name": "Elevación de piernas colgado", "name_es": "Elevación de piernas colgado", "muscle_group": "Abdomen", "category": "Calistenia"},
    {"name": "Russian twist", "name_es": "Russian twist", "muscle_group": "Abdomen", "category": "Aislamiento"},
    {"name": "Bicicleta abdominal", "name_es": "Bicicleta abdominal", "muscle_group": "Abdomen", "category": "Calistenia"},
    {"name": "Press banca con mancuernas", "name_es": "Press banca con mancuernas", "muscle_group": "Pecho", "category": "Fuerza"},
    {"name": "Remo en máquina", "name_es": "Remo en máquina", "muscle_group": "Espalda", "category": "Fuerza"},
    {"name": "Face pull", "name_es": "Face pull", "muscle_group": "Hombros", "category": "Aislamiento"},
    {"name": "Sentadilla búlgara", "name_es": "Sentadilla búlgara", "muscle_group": "Piernas", "category": "Fuerza"},
    {"name": "Curl femoral sentado", "name_es": "Curl femoral sentado", "muscle_group": "Piernas", "category": "Aislamiento"},
    {"name": "Press de hombros con mancuernas", "name_es": "Press de hombros con mancuernas", "muscle_group": "Hombros", "category": "Fuerza"},
    {"name": "Remo upright", "name_es": "Remo upright", "muscle_group": "Hombros", "category": "Fuerza"},
    {"name": "Curl inverso", "name_es": "Curl inverso", "muscle_group": "Bíceps", "category": "Aislamiento"},
    {"name": "Aperturas en polea", "name_es": "Aperturas en polea", "muscle_group": "Pecho", "category": "Aislamiento"},
    {"name": "Press declinado con barra", "name_es": "Press declinado con barra", "muscle_group": "Pecho", "category": "Fuerza"},
    {"name": "Sentadilla goblet", "name_es": "Sentadilla goblet", "muscle_group": "Piernas", "category": "Fuerza"},
    {"name": "Peso muerto con piernas rígidas", "name_es": "Peso muerto con piernas rígidas", "muscle_group": "Piernas", "category": "Fuerza"},
    {"name": "Curl de piernas en máquina", "name_es": "Curl de piernas en máquina", "muscle_group": "Piernas", "category": "Aislamiento"},
    {"name": "Elevación de pelvis", "name_es": "Elevación de pelvis", "muscle_group": "Glúteos", "category": "Fuerza"},
]


async def seed_database():
    await init_db()

    async with async_session() as session:
        result = await session.execute(select(Exercise).limit(1))
        if result.scalar_one_or_none():
            print("Ejercicios ya existen en la BD. Saltando seed.")
            return

        added_names = set()

        for fb in EXERCISE_FALLBACKS:
            ex = Exercise(
                name=fb["name"],
                name_es=fb["name_es"],
                muscle_group=fb["muscle_group"],
                category=fb["category"],
            )
            session.add(ex)
            added_names.add(fb["name"])

        await session.commit()
        print(f"✅ {len(added_names)} ejercicios guardados (modo local, sin API wger)")


if __name__ == "__main__":
    asyncio.run(seed_database())
