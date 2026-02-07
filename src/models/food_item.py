from __future__ import annotations

import uuid
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
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        alias="_id",
        description="The unique identifier for the food item.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Food Item ID",
    )

    name: str = Field(..., description="The name of the food item.", title="Food Item Name")
    state: IndianState = Field(..., description="The Indian state associated with the food item.", title="Indian State")
    type: FoodType = Field(..., description="The type of the food item (non-veg, veg, or vegan).", title="Food Type")
    allergic_ingredients: list[Allergen] = Field(
        ..., description="A list of allergens present in the food item.", title="Allergic Ingredients"
    )
    total_calories: float = Field(..., description="The total calories in the food item.", title="Total Calories")
    total_carbs_in_g: float = Field(
        ..., description="The total carbohydrates in grams in the food item.", title="Total Carbohydrates in g"
    )
    total_fats_in_g: float = Field(..., description="The total fats in grams in the food item.", title="Total Fats in g")
    total_protein_in_g: float = Field(..., description="The total protein in grams in the food item.", title="Total Protein in g")
    total_sugar_in_g: float = Field(..., description="The total sugar in grams in the food item.", title="Total Sugar in g")
    total_sodium_in_mg: float = Field(..., description="The total sodium in milligrams in the food item.", title="Total Sodium in mg")
    vitamin_content: list[str] = Field(..., description="A list of vitamins present in the food item.", title="Vitamin Content")

    image_uri: str | None = Field(None, description="The URI of the image representing the food item.", title="Image URI")

    class Config:
        extra = "ignore"
