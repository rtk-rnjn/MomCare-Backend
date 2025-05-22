from __future__ import annotations

from enum import Enum

__all__ = (
    "ExerciseType",
    "MoodType",
    "DifficultyType",
    "PreExistingCondition",
    "Intolerance",
    "DietaryPreference",
    "Country",
    "MealType",
)


class ExerciseType(Enum):
    BREATHING = "Breathing"
    STRETCHING = "Stretching"
    YOGA = "Yoga"


class MoodType(Enum):
    HAPPY = "Happy"
    SAD = "Sad"
    STRESSED = "Stressed"
    ANGRY = "Angry"


class DifficultyType(Enum):
    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"


class PreExistingCondition(Enum):
    DIABETES = "Diabetes"
    HYPERTENSION = "Hypertension"
    PCOS = "PCOS"
    ANEMIA = "Anemia"
    ASTHMA = "Asthma"
    HEART_DISEASE = "Heart Disease"
    KIDNEY_DISEASE = "Kidney Disease"


class Intolerance(Enum):
    GLUTEN = "Gluten"
    LACTOSE = "Lactose"
    EGG = "Egg"
    SEAFOOD = "Seafood"
    SOY = "Soy"
    DAIRY = "Dairy"
    WHEAT = "Wheat"


class DietaryPreference(Enum):
    VEGETARIAN = "Vegetarian"
    NON_VEGETARIAN = "Non-Vegetarian"
    VEGAN = "Vegan"
    PESCETARIAN = "Pescetarian"
    FLEXITARIAN = "Flexitarian"
    GLUTEN_FREE = "Gluten-Free"
    KETOGENIC = "Ketogenic"
    HIGH_PROTEIN = "High Protein"
    DAIRY_FREE = "Dairy-Free"


class Country(Enum):
    INDIA = "India"
    USA = "USA"
    UK = "UK"


class MealType(Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    SNACKS = "snacks"
    DINNER = "dinner"
