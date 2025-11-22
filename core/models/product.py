"""
Canonical Product Schema - The Golden Record for all products in VeloData.
"""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class ProductIdentity(BaseModel):
    """Identity fields for a Pokemon Card."""
    set_code: str = Field(..., description="Set code (e.g., 'sv2a')")
    card_number: str = Field(..., description="Card number within set (e.g., '165/165')")
    name_jp: str = Field(..., description="Japanese name of the card")
    rarity: str = Field(..., description="Rarity tier")


class ProductMetadata(BaseModel):
    """Metadata fields for source tracking."""
    image_url: str = Field(..., description="URL to card image")
    source_url: str = Field(..., description="Original source URL")


class CanonicalProduct(BaseModel):
    """
    The Golden Record Schema.
    Represents a single product in the VeloData system.
    """
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., alias="_id", description="Unique identifier (e.g., 'sv2a-165')")
    niche_type: Literal["POKEMON_CARD", "WATCH"] = Field(
        default="POKEMON_CARD",
        description="Product category"
    )
    identity: ProductIdentity = Field(..., description="Core identity fields")
    metadata: ProductMetadata = Field(..., description="Source metadata")
