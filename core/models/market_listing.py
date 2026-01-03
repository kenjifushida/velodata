"""
Market Listing Schema - Raw scraped listings from Japanese marketplaces.

Architecture: Flexible Attributes Pattern
- Core fields are common across all listings
- Niche-specific data stored in polymorphic 'attributes' dictionary
- Processing pipeline enriches listings with matching and profit calculations
"""
from typing import Literal, Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, ConfigDict


# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

# Japanese condition ranking system (used by Hard-Off, Map Camera, etc.)
ConditionRank = Literal["N", "S", "A", "B", "C", "D", "JUNK"]
"""
Japanese marketplace condition ranking:
- N: New (新品)
- S: Nearly New (未使用品)
- A: Excellent (美品)
- B: Good (良品)
- C: Fair (並品)
- D: Poor (難あり)
- JUNK: Junk (ジャンク)
"""


class MarketSource(BaseModel):
    """
    Represents a marketplace source with metadata.

    Examples:
        - Hard-Off: Japanese secondhand store chain
        - Mercari JP: Japanese C2C marketplace
        - Yahoo Auctions JP: Japanese auction platform
    """
    source_id: Literal[
        "HARDOFF",
        "MERCARI_JP",
        "YAHOO_AUCTIONS_JP",
        "SURUGA_YA",
        "MAP_CAMERA",
        "POKEMON_CENTER_ONLINE"
    ]
    display_name: str
    base_url: str

    @classmethod
    def hardoff(cls) -> "MarketSource":
        """Factory for Hard-Off source."""
        return cls(
            source_id="HARDOFF",
            display_name="Hard-Off",
            base_url="https://netmall.hardoff.co.jp"
        )

    @classmethod
    def mercari_jp(cls) -> "MarketSource":
        """Factory for Mercari JP source."""
        return cls(
            source_id="MERCARI_JP",
            display_name="Mercari Japan",
            base_url="https://jp.mercari.com"
        )

    @classmethod
    def yahoo_auctions_jp(cls) -> "MarketSource":
        """Factory for Yahoo Auctions JP source."""
        return cls(
            source_id="YAHOO_AUCTIONS_JP",
            display_name="Yahoo! Auctions Japan",
            base_url="https://auctions.yahoo.co.jp"
        )

    @classmethod
    def suruga_ya(cls) -> "MarketSource":
        """Factory for Suruga-ya source."""
        return cls(
            source_id="SURUGA_YA",
            display_name="Suruga-ya",
            base_url="https://www.suruga-ya.jp"
        )

    @classmethod
    def map_camera(cls) -> "MarketSource":
        """Factory for Map Camera source."""
        return cls(
            source_id="MAP_CAMERA",
            display_name="Map Camera",
            base_url="https://www.mapcamera.com"
        )

    @classmethod
    def pokemon_center_online(cls) -> "MarketSource":
        """Factory for Pokemon Center Online source."""
        return cls(
            source_id="POKEMON_CENTER_ONLINE",
            display_name="Pokemon Center Online",
            base_url="https://www.pokemoncenter-online.com"
        )


# ============================================================================
# MARKET LISTING MODEL
# ============================================================================

class MarketListing(BaseModel):
    """
    Represents a raw listing scraped from a marketplace.
    Stored in the 'market_listings' collection.

    The listing contains core fields common to all products, plus a flexible
    'attributes' dictionary for niche-specific data.

    Processing Pipeline:
        1. Scraper creates MarketListing with raw data
        2. Processor attempts to match to canonical_products
        3. If matched, calculates potential profit
        4. Updates is_processed and matched_canonical_id

    Examples:
        # Camera Listing from Hard-Off
        listing = MarketListing(
            _id="HARDOFF_10123456",
            niche_type="CAMERA_GEAR",
            source=MarketSource.hardoff(),
            title="Canon EOS R5 ミラーレス一眼カメラ",
            price_jpy=320000,
            url="https://netmall.hardoff.co.jp/product/10123456",
            image_urls=["https://...", "https://...", "https://..."],
            attributes={
                "brand": "Canon",
                "model_number": "EOS R5",
                "subcategory": "CAMERA",
                "subcategory_raw": "ミラーレス一眼カメラ",
                "condition_rank": "A",
                "mount": "RF",
                "megapixels": "45MP"
            }
        )

        # Watch Listing from Map Camera
        listing = MarketListing(
            _id="MAP_CAMERA_ABC123",
            niche_type="WATCH",
            source=MarketSource.map_camera(),
            title="Rolex Submariner 116610LN",
            price_jpy=1250000,
            url="https://www.mapcamera.com/item/ABC123",
            attributes={
                "brand": "Rolex",
                "model": "Submariner",
                "reference_number": "116610LN",
                "condition_rank": "A",
                "box_included": True,
                "papers_included": True
            }
        )

        # Pokemon Card Listing from Suruga-ya
        listing = MarketListing(
            _id="SURUGA_YA_987654321",
            niche_type="POKEMON_CARD",
            source=MarketSource.suruga_ya(),
            title="ピカチュウex RR sv2a 165/165",
            price_jpy=1500,
            url="https://www.suruga-ya.jp/product/987654321",
            attributes={
                "set_code": "sv2a",
                "card_number": "165",
                "rarity": "RR",
                "condition": "NM"  # Cards use different grading
            }
        )
    """

    model_config = ConfigDict(
        populate_by_name=True,
        # Allow arbitrary types for flexibility in attributes
        arbitrary_types_allowed=True,
    )

    # --- IDENTITY ---
    id: str = Field(
        ...,
        alias="_id",
        description="Unique identifier: {SOURCE}_{EXTERNAL_ID} (e.g., 'HARDOFF_10123456')"
    )

    # --- CLASSIFICATION ---
    niche_type: Literal["POKEMON_CARD", "WATCH", "CAMERA_GEAR", "LUXURY_ITEM", "VIDEOGAME", "STATIONARY", "COLLECTION_FIGURES"] = Field(
        ...,
        description="Product niche type (must match canonical_products niche types)"
    )

    source: MarketSource = Field(
        ...,
        description="Marketplace source metadata"
    )

    # --- CORE DATA (Every listing has these) ---
    title: str = Field(
        ...,
        description="Raw title from marketplace (often in Japanese)"
    )

    price_jpy: int = Field(
        ...,
        gt=0,
        description="Price in Japanese Yen (positive integer)"
    )

    url: HttpUrl = Field(
        ...,
        description="Direct URL to the listing on the marketplace"
    )

    image_urls: List[HttpUrl] = Field(
        default_factory=list,
        description="URLs to all product images from the listing detail page"
    )

    listed_at: Optional[datetime] = Field(
        None,
        description="When the seller originally listed this item on the marketplace (if available)"
    )

    # --- POLYMORPHIC ATTRIBUTES (Niche-specific data) ---
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Flexible field for niche-specific attributes"
    )

    # --- PROCESSING STATUS ---
    is_processed: bool = Field(
        default=False,
        description="Has the processor analyzed this listing?"
    )

    matched_canonical_id: Optional[str] = Field(
        None,
        description="ID of matched canonical_products document (if found)"
    )

    potential_profit_usd: Optional[float] = Field(
        None,
        description="Calculated arbitrage profit in USD (populated by processor)"
    )

    # --- METADATA ---
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this document was first created in our database (UTC)"
    )

    last_updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last time this listing was updated (UTC)"
    )

    scrape_session_id: Optional[str] = Field(
        None,
        description="Correlation ID from the scraping session"
    )

    def update_processing_status(
        self,
        matched_canonical_id: Optional[str] = None,
        potential_profit_usd: Optional[float] = None
    ):
        """
        Update the processing status of this listing.

        Args:
            matched_canonical_id: ID of matched canonical product
            potential_profit_usd: Calculated profit opportunity
        """
        self.is_processed = True
        self.matched_canonical_id = matched_canonical_id
        self.potential_profit_usd = potential_profit_usd
        self.last_updated_at = datetime.utcnow()

    def to_dict_for_db(self) -> dict:
        """
        Convert to dictionary for MongoDB insertion.

        Returns:
            Dictionary with _id alias and datetime objects
        """
        return self.model_dump(by_alias=True, mode='json')


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_hardoff_listing(
    external_id: str,
    niche_type: Literal["POKEMON_CARD", "WATCH", "CAMERA_GEAR", "LUXURY_ITEM", "VIDEOGAME"],
    title: str,
    price_jpy: int,
    url: str,
    attributes: Dict[str, Any],
    image_urls: Optional[List[str]] = None,
    listed_at: Optional[datetime] = None,
    scrape_session_id: Optional[str] = None,
) -> MarketListing:
    """
    Factory function for creating Hard-Off market listings.

    Args:
        external_id: Hard-Off's internal product ID
        niche_type: Product category
        title: Product title (Japanese)
        price_jpy: Price in Yen
        url: Direct URL to listing
        attributes: Niche-specific attributes
        image_urls: List of product image URLs
        listed_at: When the seller originally listed the item (if available)
        scrape_session_id: Scraping session correlation ID

    Returns:
        MarketListing instance

    Example:
        listing = create_hardoff_listing(
            external_id="10123456",
            niche_type="CAMERA_GEAR",
            title="Canon EOS R5 ミラーレス一眼カメラ",
            price_jpy=320000,
            url="https://netmall.hardoff.co.jp/product/10123456",
            image_urls=["https://...", "https://..."],
            attributes={
                "brand": "Canon",
                "model_number": "EOS R5",
                "subcategory": "CAMERA",
                "subcategory_raw": "ミラーレス一眼カメラ",
                "condition_rank": "A"
            }
        )
    """
    return MarketListing(
        _id=f"HARDOFF_{external_id}",
        niche_type=niche_type,
        source=MarketSource.hardoff(),
        title=title,
        price_jpy=price_jpy,
        url=url,
        image_urls=image_urls or [],
        listed_at=listed_at,
        attributes=attributes,
        scrape_session_id=scrape_session_id,
    )


def create_mercari_listing(
    external_id: str,
    niche_type: Literal["POKEMON_CARD", "WATCH", "CAMERA_GEAR"],
    title: str,
    price_jpy: int,
    url: str,
    attributes: Dict[str, Any],
    image_url: Optional[str] = None,
    listed_at: Optional[datetime] = None,
    scrape_session_id: Optional[str] = None,
) -> MarketListing:
    """
    Factory function for creating Mercari JP market listings.

    Args:
        external_id: Mercari's internal product ID
        niche_type: Product category
        title: Product title (Japanese)
        price_jpy: Price in Yen
        url: Direct URL to listing
        attributes: Niche-specific attributes
        image_url: Product image URL
        listed_at: When the seller originally listed the item (if available)
        scrape_session_id: Scraping session correlation ID

    Returns:
        MarketListing instance
    """
    return MarketListing(
        _id=f"MERCARI_JP_{external_id}",
        niche_type=niche_type,
        source=MarketSource.mercari_jp(),
        title=title,
        price_jpy=price_jpy,
        url=url,
        image_url=image_url,
        listed_at=listed_at,
        attributes=attributes,
        scrape_session_id=scrape_session_id,
    )


def create_suruga_ya_listing(
    external_id: str,
    niche_type: Literal["POKEMON_CARD", "WATCH", "CAMERA_GEAR"],
    title: str,
    price_jpy: int,
    url: str,
    attributes: Dict[str, Any],
    image_url: Optional[str] = None,
    listed_at: Optional[datetime] = None,
    scrape_session_id: Optional[str] = None,
) -> MarketListing:
    """
    Factory function for creating Suruga-ya market listings.

    Args:
        external_id: Suruga-ya's internal product ID
        niche_type: Product category
        title: Product title (Japanese)
        price_jpy: Price in Yen
        url: Direct URL to listing
        attributes: Niche-specific attributes
        image_url: Product image URL
        listed_at: When the seller originally listed the item (if available)
        scrape_session_id: Scraping session correlation ID

    Returns:
        MarketListing instance
    """
    return MarketListing(
        _id=f"SURUGA_YA_{external_id}",
        niche_type=niche_type,
        source=MarketSource.suruga_ya(),
        title=title,
        price_jpy=price_jpy,
        url=url,
        image_url=image_url,
        listed_at=listed_at,
        attributes=attributes,
        scrape_session_id=scrape_session_id,
    )


def create_map_camera_listing(
    external_id: str,
    niche_type: Literal["WATCH", "CAMERA_GEAR"],
    title: str,
    price_jpy: int,
    url: str,
    attributes: Dict[str, Any],
    image_url: Optional[str] = None,
    listed_at: Optional[datetime] = None,
    scrape_session_id: Optional[str] = None,
) -> MarketListing:
    """
    Factory function for creating Map Camera market listings.

    Args:
        external_id: Map Camera's internal product ID
        niche_type: Product category (watches or camera gear)
        title: Product title (Japanese)
        price_jpy: Price in Yen
        url: Direct URL to listing
        attributes: Niche-specific attributes
        image_url: Product image URL
        listed_at: When the seller originally listed the item (if available)
        scrape_session_id: Scraping session correlation ID

    Returns:
        MarketListing instance
    """
    return MarketListing(
        _id=f"MAP_CAMERA_{external_id}",
        niche_type=niche_type,
        source=MarketSource.map_camera(),
        title=title,
        price_jpy=price_jpy,
        url=url,
        image_url=image_url,
        listed_at=listed_at,
        attributes=attributes,
        scrape_session_id=scrape_session_id,
    )


# ============================================================================
# ATTRIBUTE HELPERS (Type-safe attribute extraction)
# ============================================================================

class CameraGearAttributes:
    """
    Helper class for type-safe camera gear attribute access.

    Common attributes for camera gear from Japanese marketplaces:
    - condition_rank: Japanese ranking (N, S, A, B, C, D, JUNK)
    - brand: Manufacturer (Canon, Nikon, Sony, etc.)
    - model_number: Model name/number (e.g., "EOS R5", "RF 24-70mm")
    - subcategory: Equipment type (CAMERA, LENS, VIDEO_CAMERA, VIDEO_ACCESSORY, PHOTO_ACCESSORY)
    - subcategory_raw: Original Japanese subcategory name (e.g., "デジタルカメラ", "レンズ")
    - mount: Lens mount (EF, RF, E, Z, etc.)
    - megapixels: Sensor resolution
    - sensor_size: Full-frame, APS-C, Micro Four Thirds, etc.
    - focal_length: For lenses (e.g., "24-70mm")
    - aperture: For lenses (e.g., "f/2.8")
    """

    @staticmethod
    def extract(attributes: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """
        Extract camera gear attributes safely.

        Args:
            attributes: Raw attributes dictionary

        Returns:
            Dictionary with typed camera gear fields
        """
        return {
            "brand": attributes.get("brand"),
            "model_number": attributes.get("model_number"),
            "subcategory": attributes.get("subcategory"),  # CAMERA, LENS, VIDEO_CAMERA, etc.
            "subcategory_raw": attributes.get("subcategory_raw"),  # Original Japanese text
            "condition_rank": attributes.get("condition_rank"),  # N, S, A, B, C, D, JUNK
            "mount": attributes.get("mount"),
            "megapixels": attributes.get("megapixels"),
            "sensor_size": attributes.get("sensor_size"),
            "focal_length": attributes.get("focal_length"),  # For lenses
            "aperture": attributes.get("aperture"),  # For lenses
            "shutter_count": attributes.get("shutter_count"),  # For cameras
            "accessories": attributes.get("accessories"),  # Included items
        }


class WatchAttributes:
    """
    Helper class for type-safe watch attribute access.

    Common attributes for watches from Japanese marketplaces:
    - condition_rank: Japanese ranking (N, S, A, B, C, D, JUNK)
    - brand: Manufacturer (Rolex, Omega, Seiko, etc.)
    - model: Model name
    - reference_number: Official reference/model number
    - serial_number: Unique serial number
    - case_size: Diameter (e.g., "40mm")
    - movement: Automatic, Quartz, Manual
    - box_included: Original box present
    - papers_included: Original papers/warranty present
    """

    @staticmethod
    def extract(attributes: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """
        Extract watch attributes safely.

        Args:
            attributes: Raw attributes dictionary

        Returns:
            Dictionary with typed watch fields
        """
        return {
            "brand": attributes.get("brand"),
            "model": attributes.get("model"),
            "reference_number": attributes.get("reference_number"),
            "serial_number": attributes.get("serial_number"),
            "condition_rank": attributes.get("condition_rank"),  # N, S, A, B, C, D, JUNK
            "case_size": attributes.get("case_size"),
            "movement": attributes.get("movement"),
            "box_included": attributes.get("box_included"),
            "papers_included": attributes.get("papers_included"),
            "year": attributes.get("year"),
            "service_history": attributes.get("service_history"),
        }


class PokemonCardAttributes:
    """
    Helper class for type-safe Pokemon card attribute access.

    Common attributes for Pokemon cards from Japanese marketplaces:
    - set_code: Set identifier (e.g., "sv2a", "sv10")
    - card_number: Card number within set
    - rarity: Rarity tier (RR, SR, UR, etc.)
    - condition: Card condition (NM, LP, MP, HP, DMG)
    - language: Card language (usually "JP")
    - graded: Is the card graded?
    - grade: PSA/BGS grade if applicable
    """

    @staticmethod
    def extract(attributes: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """
        Extract Pokemon card attributes safely.

        Args:
            attributes: Raw attributes dictionary

        Returns:
            Dictionary with typed Pokemon card fields
        """
        return {
            "set_code": attributes.get("set_code"),
            "card_number": attributes.get("card_number"),
            "rarity": attributes.get("rarity"),
            "condition": attributes.get("condition"),  # NM, LP, MP, HP, DMG
            "language": attributes.get("language", "JP"),
            "graded": attributes.get("graded"),
            "grade": attributes.get("grade"),
            "card_name": attributes.get("card_name"),
        }


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def validate_condition_rank(rank: str) -> bool:
    """
    Validate Japanese condition ranking.

    Args:
        rank: Condition rank string

    Returns:
        True if valid, False otherwise
    """
    valid_ranks = {"N", "S", "A", "B", "C", "D", "JUNK"}
    return rank.upper() in valid_ranks


def normalize_condition_rank(rank: str) -> ConditionRank:
    """
    Normalize condition rank to standard format.

    Args:
        rank: Raw condition rank (may be lowercase, Japanese, etc.)

    Returns:
        Normalized ConditionRank

    Raises:
        ValueError: If rank is invalid
    """
    # Convert to uppercase
    rank_upper = rank.upper()

    # Handle Japanese characters
    japanese_mapping = {
        "新品": "N",
        "未使用品": "S",
        "美品": "A",
        "良品": "B",
        "並品": "C",
        "難あり": "D",
        "ジャンク": "JUNK",
    }

    if rank_upper in japanese_mapping:
        return japanese_mapping[rank_upper]

    if validate_condition_rank(rank_upper):
        return rank_upper

    raise ValueError(f"Invalid condition rank: {rank}")
