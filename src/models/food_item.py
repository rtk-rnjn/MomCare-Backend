from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, TypedDict

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from typing_extensions import NotRequired


class IndianState(StrEnum):
    ANDAMAN = "andaman"
    ANDHRA_PRADESH = "andhra pradesh"
    ARUNACHAL_PRADESH = "arunachal pradesh"
    ASSAM = "assam"
    BIHAR = "bihar"
    CHANDIGARH = "chandigarh"
    CHHATTISGARH = "chhattisgarh"
    DADRA_AND_NAGAR_HAVELI = "dadra and nagar haveli"
    DAMAN_AND_DIU = "daman and diu"
    DELHI = "delhi"
    GOA = "goa"
    GUJARAT = "gujarat"
    HARYANA = "haryana"
    HIMACHAL_PRADESH = "himachal pradesh"
    JAMMU_AND_KASHMIR = "jammu and kashmir"
    JHARKHAND = "jharkhand"
    KARNATAKA = "karnataka"
    KERALA = "kerala"
    LADAKH = "ladakh"
    LAKSHADWEEP = "lakshadweep"
    MADHYA_PRADESH = "madhya pradesh"
    MAHARASHTRA = "maharashtra"
    MANIPUR = "manipur"
    MEGHALAYA = "meghalaya"
    MIZORAM = "mizoram"
    NAGALAND = "nagaland"
    ODISHA = "odisha"
    PUDUCHERRY = "puducherry"
    PUNJAB = "punjab"
    RAJASTHAN = "rajasthan"
    SIKKIM = "sikkim"
    TAMIL_NADU = "tamil nadu"
    TELANGANA = "telangana"
    TRIPURA = "tripura"
    UTTAR_PRADESH = "uttar pradesh"
    UTTARAKHAND = "uttarakhand"
    WEST_BENGAL = "west bengal"


class Allergen(StrEnum):
    BANANA = "banana"
    BEANS = "beans"
    BEEF = "beef"
    BLACK_EYED_PEAS = "black-eyed peas"
    BREADFRUIT = "breadfruit"
    CASHEW = "cashew"
    CHICKEN = "chicken"
    CHICKPEAS = "chickpeas"
    CHILI = "chili"
    CLAMS = "clams"
    COCONUT = "coconut"
    CRAB = "crab"
    DAIRY = "dairy"
    DUCK = "duck"
    EGG = "egg"
    EGGS = "eggs"
    FISH = "fish"
    FISH_ROE = "fish roe"
    GARLIC = "garlic"
    GLUTEN = "gluten"
    GLUTEN_FREE = "gluten-free"
    KOKUM = "kokum"
    MACKEREL = "mackerel"
    MANGO = "mango"
    MEAT = "meat"
    MUNG_BEANS = "mung beans"
    MUSHROOMS = "mushrooms"
    MUSSELS = "mussels"
    MUTTON = "mutton"
    NUTS = "nuts"
    PEANUTS = "peanuts"
    PORK = "pork"
    PRAWN = "prawn"
    PRAWNS = "prawns"
    RAW_MANGO = "raw mango"
    RICE = "rice"
    RICE_FLOUR = "rice flour"
    SEAFOOD = "seafood"
    SESAME = "sesame"
    SHARK = "shark"
    SHELLFISH = "shellfish"
    SHRIMP = "shrimp"
    SILKWORM = "silkworm"
    SOY = "soy"
    SOYBEAN = "soybean"
    SPICES = "spices"
    SUGAR = "sugar"
    TAMARIND = "tamarind"
    TAPIOCA = "tapioca"
    VINEGAR = "vinegar"


class FoodType(StrEnum):
    NON_VEG = "non-veg"
    VEG = "veg"
    VEGAN = "vegan"


class FoodItemDict(TypedDict):
    _id: NotRequired[str]

    name: str
    state: IndianState
    type: FoodType
    allergic_ingredients: list[Allergen]
    total_calories: float
    total_carbs_in_g: float
    total_fats_in_g: float
    total_protein_in_g: float
    total_sugar_in_g: float
    total_sodium_in_mg: float
    vitamin_content: list[str]
    image_uri: NotRequired[str] | None


class FoodItemModel(BaseModel):
    id: str = Field(..., alias="_id")

    name: str
    state: IndianState
    type: FoodType
    allergic_ingredients: list[Allergen]
    total_calories: float
    total_carbs_in_g: float
    total_fats_in_g: float
    total_protein_in_g: float
    total_sugar_in_g: float
    total_sodium_in_mg: float
    vitamin_content: list[str]
    image_uri: str | None = None

    class Config:
        extra = "ignore"
