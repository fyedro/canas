import uuid
from datetime import date, datetime, time
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, Date, DateTime, Time,
    ForeignKey, Enum as SqlEnum
)
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class MuscleGroup(str, enum.Enum):
    PECHO = "Pecho"
    ESPALDA = "Espalda"
    HOMBROS = "Hombros"
    BICEPS = "Bíceps"
    TRICEPS = "Tríceps"
    PIERNAS = "Piernas"
    GLUTEOS = "Glúteos"
    ABDOMEN = "Abdomen"
    CARDIO = "Cardio"
    CUERPO_COMPLETO = "Cuerpo completo"


class MealType(str, enum.Enum):
    DESAYUNO = "Desayuno"
    COMIDA = "Comida"
    CENA = "Cena"
    SNACK = "Snack"


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    nombre = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    routines = relationship("Routine", back_populates="user", cascade="all, delete-orphan")
    workouts = relationship("Workout", back_populates="user", cascade="all, delete-orphan")
    meals = relationship("Meal", back_populates="user", cascade="all, delete-orphan")
    measurements = relationship("BodyMeasurement", back_populates="user", cascade="all, delete-orphan")
    nutrition_goals = relationship("DailyNutrition", back_populates="user", cascade="all, delete-orphan")
    diet_plans = relationship("DietPlan", back_populates="user", cascade="all, delete-orphan")
    diet_assignments = relationship("DietPlanAssignment", back_populates="user", cascade="all, delete-orphan")


class Exercise(Base):
    __tablename__ = "exercises"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, index=True)
    name_es = Column(String(200), nullable=True)
    muscle_group = Column(String(50), nullable=True)
    category = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    image_url_secondary = Column(String(500), nullable=True)
    wger_id = Column(Integer, unique=True, nullable=True)
    is_custom = Column(Boolean, default=False)
    user_id = Column(String, ForeignKey("user_profiles.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Routine(Base):
    __tablename__ = "routines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("user_profiles.id"), nullable=False)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    dia_semana = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("UserProfile", back_populates="routines")
    exercises = relationship("RoutineExercise", back_populates="routine",
                             cascade="all, delete-orphan",
                             order_by="RoutineExercise.orden")


class RoutineExercise(Base):
    __tablename__ = "routine_exercises"

    id = Column(Integer, primary_key=True, autoincrement=True)
    routine_id = Column(Integer, ForeignKey("routines.id"), nullable=False)
    exercise_id = Column(Integer, ForeignKey("exercises.id"), nullable=True)
    exercise_name = Column(String(200), nullable=False)
    sets = Column(Integer, nullable=False, default=3)
    min_reps = Column(Integer, nullable=True)
    max_reps = Column(Integer, nullable=True)
    peso = Column(Float, nullable=True)
    orden = Column(Integer, nullable=False, default=0)
    rest_time = Column(Integer, nullable=True, default=90)
    notas = Column(Text, nullable=True)

    routine = relationship("Routine", back_populates="exercises")
    exercise = relationship("Exercise")


class Workout(Base):
    __tablename__ = "workouts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("user_profiles.id"), nullable=False)
    routine_id = Column(Integer, ForeignKey("routines.id"), nullable=True)
    nombre = Column(String(200), nullable=False)
    fecha = Column(Date, nullable=False, default=date.today)
    hora_inicio = Column(DateTime, nullable=True)
    hora_fin = Column(DateTime, nullable=True)
    duracion = Column(Integer, nullable=True)
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("UserProfile", back_populates="workouts")
    routine = relationship("Routine")
    sets = relationship("WorkoutSet", back_populates="workout",
                        cascade="all, delete-orphan",
                        order_by="WorkoutSet.exercise_order, WorkoutSet.set_number")


class WorkoutSet(Base):
    __tablename__ = "workout_sets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workout_id = Column(Integer, ForeignKey("workouts.id"), nullable=False)
    exercise_name = Column(String(200), nullable=False)
    exercise_order = Column(Integer, nullable=False, default=0)
    set_number = Column(Integer, nullable=False)
    weight = Column(Float, nullable=True)
    reps = Column(Integer, nullable=True)
    rpe = Column(Float, nullable=True)
    completed = Column(Boolean, default=True)
    rest_time = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    workout = relationship("Workout", back_populates="sets")


class Meal(Base):
    __tablename__ = "meals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("user_profiles.id"), nullable=False)
    fecha = Column(Date, nullable=False, default=date.today)
    tipo = Column(String(20), nullable=False)
    hora = Column(Time, nullable=True)
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("UserProfile", back_populates="meals")
    foods = relationship("FoodItem", back_populates="meal", cascade="all, delete-orphan")


class FoodItem(Base):
    __tablename__ = "food_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meal_id = Column(Integer, ForeignKey("meals.id"), nullable=False)
    food_name = Column(String(300), nullable=False)
    cantidad = Column(Float, nullable=False, default=100)
    unidad = Column(String(20), nullable=False, default="g")
    calorias = Column(Float, nullable=True)
    proteinas = Column(Float, nullable=True)
    carbs = Column(Float, nullable=True)
    grasas = Column(Float, nullable=True)
    fibra = Column(Float, nullable=True)
    imagen_url = Column(String(500), nullable=True)
    barcode = Column(String(50), nullable=True)

    meal = relationship("Meal", back_populates="foods")


class BodyMeasurement(Base):
    __tablename__ = "body_measurements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("user_profiles.id"), nullable=False)
    fecha = Column(Date, nullable=False, default=date.today)
    peso = Column(Float, nullable=True)
    grasa_corporal = Column(Float, nullable=True)
    musculo = Column(Float, nullable=True)
    agua = Column(Float, nullable=True)
    hueso = Column(Float, nullable=True)
    imc = Column(Float, nullable=True)
    grasa_visceral = Column(Float, nullable=True)
    metabolismo_basal = Column(Float, nullable=True)
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("UserProfile", back_populates="measurements")


class DailyNutrition(Base):
    __tablename__ = "daily_nutrition"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("user_profiles.id"), nullable=False)
    fecha = Column(Date, nullable=False, default=date.today)
    calorias_objetivo = Column(Float, nullable=True, default=2000)
    proteinas_objetivo = Column(Float, nullable=True, default=150)
    carbs_objetivo = Column(Float, nullable=True, default=250)
    grasas_objetivo = Column(Float, nullable=True, default=65)

    user = relationship("UserProfile", back_populates="nutrition_goals")


class DietPlan(Base):
    __tablename__ = "diet_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("user_profiles.id"), nullable=False)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("UserProfile")
    meals = relationship("DietPlanMeal", back_populates="plan",
                         cascade="all, delete-orphan",
                         order_by="DietPlanMeal.orden")
    assignments = relationship("DietPlanAssignment", back_populates="plan",
                               cascade="all, delete-orphan")


class DietPlanMeal(Base):
    __tablename__ = "diet_plan_meals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    diet_plan_id = Column(Integer, ForeignKey("diet_plans.id"), nullable=False)
    tipo = Column(String(20), nullable=False)
    notas = Column(Text, nullable=True)
    orden = Column(Integer, nullable=False, default=0)

    plan = relationship("DietPlan", back_populates="meals")
    foods = relationship("DietPlanFood", back_populates="meal",
                         cascade="all, delete-orphan")


class DietPlanFood(Base):
    __tablename__ = "diet_plan_foods"

    id = Column(Integer, primary_key=True, autoincrement=True)
    diet_plan_meal_id = Column(Integer, ForeignKey("diet_plan_meals.id"), nullable=False)
    food_name = Column(String(300), nullable=False)
    cantidad = Column(Float, nullable=True)
    unidad = Column(String(30), nullable=True, default="g")
    calorias = Column(Float, nullable=True)
    proteinas = Column(Float, nullable=True)
    carbs = Column(Float, nullable=True)
    grasas = Column(Float, nullable=True)
    notas = Column(Text, nullable=True)

    meal = relationship("DietPlanMeal", back_populates="foods")


class DietPlanAssignment(Base):
    __tablename__ = "diet_plan_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("user_profiles.id"), nullable=False)
    diet_plan_id = Column(Integer, ForeignKey("diet_plans.id"), nullable=False)
    fecha = Column(Date, nullable=False)

    user = relationship("UserProfile")
    plan = relationship("DietPlan", back_populates="assignments")
