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

class TCGIdentity(BaseModel):
    """Identity fields specific to Trading Card Games (Pokemon, Yu-Gi-Oh!, One Piece, Magic)."""

    niche_type: Literal["TCG"] = Field(
        default="TCG",
        description="Discriminator field for trading card games"
    )
    game: Literal["POKEMON", "YUGIOH", "ONE_PIECE", "MAGIC"] = Field(
        ...,
        description="TCG game type"
    )
    set_code: str = Field(..., description="Set code (e.g., 'sv2a', 'BODE-EN', 'OP01', 'BRO')")
    card_number: str = Field(..., description="Card number within set (e.g., '165', '001')")
    name_jp: str | None = Field(None, description="Japanese name of the card (if applicable)")
    name_en: str | None = Field(None, description="English name of the card (if applicable)")
    rarity: str | None = Field(None, description="Rarity tier (e.g., 'RR', 'SR', 'UR', 'Secret Rare')")
    language: str | None = Field(default="JP", description="Card language (JP, EN, KO, etc.)")

    def generate_id(self) -> str:
        """Generate unique product ID for TCG cards."""
        game_prefix = self.game.lower()
        return f"{game_prefix}-{self.set_code}-{self.card_number}"


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
    Union[TCGIdentity, WatchIdentity, CameraGearIdentity],
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
        # TCG Card (Pokemon)
        product = CanonicalProduct(
            _id="pokemon-sv2a-165",
            identity=TCGIdentity(
                niche_type="TCG",
                game="POKEMON",
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
    def niche_type(self) -> Literal["TCG", "WATCH", "CAMERA_GEAR"]:
        """Convenience property to access niche type."""
        return self.identity.niche_type


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_tcg_product(
    game: Literal["POKEMON", "YUGIOH", "ONE_PIECE", "MAGIC"],
    set_code: str,
    card_number: str,
    image_url: str,
    source_url: str,
    name_jp: str | None = None,
    name_en: str | None = None,
    rarity: str | None = None,
    language: str | None = "JP",
) -> CanonicalProduct:
    """
    Factory function for creating TCG products.
    Handles ID generation automatically.

    Args:
        game: TCG game type (POKEMON, YUGIOH, ONE_PIECE, MAGIC)
        set_code: Set code (e.g., 'sv2a', 'BODE-EN', 'OP01', 'BRO')
        card_number: Card number within set
        image_url: URL to product image
        source_url: Original source URL
        name_jp: Japanese name (optional)
        name_en: English name (optional)
        rarity: Rarity tier (optional)
        language: Card language (default: JP)

    Returns:
        CanonicalProduct with TCG identity

    Examples:
        # Pokemon card
        product = create_tcg_product(
            game="POKEMON",
            set_code="sv2a",
            card_number="165",
            name_jp="ピカチュウex",
            rarity="RR",
            image_url="https://...",
            source_url="https://..."
        )

        # Yu-Gi-Oh! card
        product = create_tcg_product(
            game="YUGIOH",
            set_code="BODE-EN",
            card_number="001",
            name_en="Blue-Eyes White Dragon",
            rarity="Secret Rare",
            image_url="https://...",
            source_url="https://...",
            language="EN"
        )
    """
    identity = TCGIdentity(
        game=game,
        set_code=set_code,
        card_number=card_number,
        name_jp=name_jp,
        name_en=name_en,
        rarity=rarity,
        language=language,
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

def is_tcg(product: CanonicalProduct) -> bool:
    """Type guard: Check if product is a TCG card."""
    return isinstance(product.identity, TCGIdentity)


def is_tcg_game(product: CanonicalProduct, game: Literal["POKEMON", "YUGIOH", "ONE_PIECE", "MAGIC"]) -> bool:
    """Type guard: Check if product is a specific TCG game."""
    return is_tcg(product) and product.identity.game == game


def is_watch(product: CanonicalProduct) -> bool:
    """Type guard: Check if product is a watch."""
    return isinstance(product.identity, WatchIdentity)


def is_camera_gear(product: CanonicalProduct) -> bool:
    """Type guard: Check if product is camera gear."""
    return isinstance(product.identity, CameraGearIdentity)
