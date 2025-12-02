"""
Canonical Product Schema - The Golden Record for all products in VeloData.

Architecture: Polymorphic Identity System using Discriminated Unions
- Each niche type has its own identity model
- Type-safe validation ensures data integrity
- Extensible: Add new niches without modifying existing code
"""
from typing import Literal, Union, Annotated
from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# BASE MODELS
# ============================================================================

class ProductMetadata(BaseModel):
    """
    Base metadata fields for source tracking.
    Common across all product types.
    """
    image_url: str = Field(..., description="URL to product image")
    source_url: str = Field(..., description="Original source URL")


# ============================================================================
# NICHE-SPECIFIC IDENTITY MODELS (Discriminated Union Pattern)
# ============================================================================

class PokemonCardIdentity(BaseModel):
    """Identity fields specific to Pokemon Trading Cards."""

    niche_type: Literal["POKEMON_CARD"] = Field(
        default="POKEMON_CARD",
        description="Discriminator field for Pokemon cards"
    )
    set_code: str = Field(..., description="Set code (e.g., 'sv2a', 'sv10')")
    card_number: str = Field(..., description="Card number within set (e.g., '165/165')")
    name_jp: str = Field(..., description="Japanese name of the card")
    rarity: str = Field(..., description="Rarity tier (e.g., 'RR', 'SR', 'UR')")

    def generate_id(self) -> str:
        """Generate unique product ID for Pokemon cards."""
        return f"{self.set_code}-{self.card_number}"


class WatchIdentity(BaseModel):
    """Identity fields specific to Luxury Watches."""

    niche_type: Literal["WATCH"] = Field(
        default="WATCH",
        description="Discriminator field for watches"
    )
    brand: str = Field(..., description="Watch brand (e.g., 'Rolex', 'Patek Philippe')")
    model: str = Field(..., description="Model name (e.g., 'Submariner', 'Nautilus')")
    reference_number: str = Field(..., description="Reference/model number (e.g., '126610LN')")
    serial_number: str | None = Field(None, description="Serial number (if applicable)")
    production_year: int | None = Field(None, description="Year of production")

    def generate_id(self) -> str:
        """Generate unique product ID for watches."""
        # Use serial if available, otherwise use reference number
        unique_part = self.serial_number or self.reference_number
        return f"{self.brand.lower()}-{unique_part}".replace(" ", "-")


class CameraGearIdentity(BaseModel):
    """Identity fields specific to Camera Gear and Photography Equipment."""

    niche_type: Literal["CAMERA_GEAR"] = Field(
        default="CAMERA_GEAR",
        description="Discriminator field for camera gear"
    )
    brand: str = Field(..., description="Camera gear brand (e.g., 'Canon', 'Sony', 'Nikon')")
    model_number: str = Field(..., description="Model number (e.g., 'EOS R5', 'RF 24-70mm f/2.8')")
    subcategory: Literal["CAMERA", "LENS", "VIDEO_CAMERA", "VIDEO_ACCESSORY", "PHOTO_ACCESSORY"] = Field(
        ...,
        description="Equipment subcategory"
    )
    condition: str | None = Field(None, description="Condition (e.g., 'New', 'Used - Excellent', 'Refurbished')")
    serial_number: str | None = Field(None, description="Serial number (if available)")

    def generate_id(self) -> str:
        """Generate unique product ID for camera gear."""
        # Sanitize brand and model for ID
        brand_part = self.brand.lower().replace(" ", "-")
        model_part = self.model_number.lower().replace(" ", "-").replace("/", "-")
        subcategory_part = self.subcategory.lower()

        # Use serial if available, otherwise use brand-subcategory-model
        if self.serial_number:
            return f"{brand_part}-{self.serial_number}"
        else:
            return f"{brand_part}-{subcategory_part}-{model_part}"


# ============================================================================
# DISCRIMINATED UNION TYPE
# ============================================================================

# This is the key architectural pattern: Pydantic will automatically
# validate and route to the correct identity type based on niche_type
ProductIdentity = Annotated[
    Union[PokemonCardIdentity, WatchIdentity, CameraGearIdentity],
    Field(discriminator="niche_type")
]


# ============================================================================
# CANONICAL PRODUCT MODEL
# ============================================================================

class CanonicalProduct(BaseModel):
    """
    The Golden Record Schema.

    Represents a single product in the VeloData system.
    Uses polymorphic identity models based on niche_type.

    Architecture:
    - Identity is polymorphic (Pokemon cards vs. Watches have different fields)
    - Metadata is common across all products
    - Type-safe validation via discriminated unions
    - Extensible: Add new niches by creating new Identity models

    Examples:
        # Pokemon Card
        product = CanonicalProduct(
            _id="sv2a-165",
            identity=PokemonCardIdentity(
                niche_type="POKEMON_CARD",
                set_code="sv2a",
                card_number="165",
                name_jp="ピカチュウex",
                rarity="RR"
            ),
            metadata=ProductMetadata(
                image_url="https://...",
                source_url="https://..."
            )
        )

        # Watch
        product = CanonicalProduct(
            _id="rolex-126610ln-abc123",
            identity=WatchIdentity(
                niche_type="WATCH",
                brand="Rolex",
                model="Submariner",
                reference_number="126610LN",
                serial_number="ABC123"
            ),
            metadata=ProductMetadata(
                image_url="https://...",
                source_url="https://..."
            )
        )
    """
    model_config = ConfigDict(
        populate_by_name=True,
        # Use union mode to properly handle discriminated unions
        # This ensures the discriminator field is checked first
    )

    id: str = Field(
        ...,
        alias="_id",
        description="Unique identifier (format depends on niche type)"
    )
    identity: ProductIdentity = Field(
        ...,
        description="Polymorphic identity fields (varies by niche_type)"
    )
    metadata: ProductMetadata = Field(
        ...,
        description="Source metadata (common across all products)"
    )

    @property
    def niche_type(self) -> Literal["POKEMON_CARD", "WATCH", "CAMERA_GEAR"]:
        """Convenience property to access niche type."""
        return self.identity.niche_type


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_pokemon_card_product(
    set_code: str,
    card_number: str,
    name_jp: str,
    rarity: str,
    image_url: str,
    source_url: str,
) -> CanonicalProduct:
    """
    Factory function for creating Pokemon card products.
    Handles ID generation automatically.
    """
    identity = PokemonCardIdentity(
        set_code=set_code,
        card_number=card_number,
        name_jp=name_jp,
        rarity=rarity,
    )

    return CanonicalProduct(
        _id=identity.generate_id(),
        identity=identity,
        metadata=ProductMetadata(
            image_url=image_url,
            source_url=source_url,
        ),
    )


def create_watch_product(
    brand: str,
    model: str,
    reference_number: str,
    image_url: str,
    source_url: str,
    serial_number: str | None = None,
    production_year: int | None = None,
) -> CanonicalProduct:
    """
    Factory function for creating watch products.
    Handles ID generation automatically.
    """
    identity = WatchIdentity(
        brand=brand,
        model=model,
        reference_number=reference_number,
        serial_number=serial_number,
        production_year=production_year,
    )

    return CanonicalProduct(
        _id=identity.generate_id(),
        identity=identity,
        metadata=ProductMetadata(
            image_url=image_url,
            source_url=source_url,
        ),
    )


def create_camera_gear_product(
    brand: str,
    model_number: str,
    subcategory: Literal["CAMERA", "LENS", "VIDEO_CAMERA", "VIDEO_ACCESSORY", "PHOTO_ACCESSORY"],
    image_url: str,
    source_url: str,
    condition: str | None = None,
    serial_number: str | None = None,
) -> CanonicalProduct:
    """
    Factory function for creating camera gear products.
    Handles ID generation automatically.

    Args:
        brand: Camera gear brand (e.g., 'Canon', 'Sony', 'Nikon')
        model_number: Model number (e.g., 'EOS R5', 'RF 24-70mm f/2.8')
        subcategory: Equipment type (CAMERA, LENS, VIDEO_CAMERA, etc.)
        image_url: URL to product image
        source_url: Original source URL
        condition: Condition (e.g., 'New', 'Used - Excellent')
        serial_number: Serial number (if available)

    Returns:
        CanonicalProduct with camera gear identity
    """
    identity = CameraGearIdentity(
        brand=brand,
        model_number=model_number,
        subcategory=subcategory,
        condition=condition,
        serial_number=serial_number,
    )

    return CanonicalProduct(
        _id=identity.generate_id(),
        identity=identity,
        metadata=ProductMetadata(
            image_url=image_url,
            source_url=source_url,
        ),
    )


# ============================================================================
# TYPE GUARDS (for type-safe access)
# ============================================================================

def is_pokemon_card(product: CanonicalProduct) -> bool:
    """Type guard: Check if product is a Pokemon card."""
    return isinstance(product.identity, PokemonCardIdentity)


def is_watch(product: CanonicalProduct) -> bool:
    """Type guard: Check if product is a watch."""
    return isinstance(product.identity, WatchIdentity)


def is_camera_gear(product: CanonicalProduct) -> bool:
    """Type guard: Check if product is camera gear."""
    return isinstance(product.identity, CameraGearIdentity)
