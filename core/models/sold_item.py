"""
Sold Item Aggregation Schema - Daily/Monthly price aggregations from SNKRDUNK and eBay.

Architecture: Pre-computed aggregations only (no individual sale records)
- Daily aggregations: Scraped daily, stored per product/condition/source
- Monthly aggregations: Computed from daily data for trend analysis
- All prices normalized to JPY for cross-marketplace comparison

Collections:
- sold_items_daily_agg: Pre-computed daily statistics
- sold_items_monthly_agg: Monthly trend aggregations

Usage:
    # Create daily aggregation from scraping SNKRDUNK
    agg = create_snkrdunk_daily_agg(
        canonical_product_id="pokemon-sv2a-165",
        niche_type="TCG",
        rank="PSA10",
        sale_date=date(2024, 1, 15),
        min_price_jpy=14000,
        max_price_jpy=16500,
        avg_price_jpy=15200.0,
        sale_count=5,
    )

    # Create daily aggregation from scraping eBay
    agg = create_ebay_daily_agg(
        canonical_product_id="pokemon-sv2a-165",
        niche_type="TCG",
        normalized_rank="PSA10",
        sale_date=date(2024, 1, 15),
        min_price_jpy=14500,
        max_price_jpy=16000,
        avg_price_jpy=15300.0,
        sale_count=8,
        avg_price_usd=102.0,
    )
"""
from typing import Literal, Optional, Dict, Any, List
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

class MarketplaceSource(str, Enum):
    """Supported marketplaces for sold item data."""
    SNKRDUNK = "SNKRDUNK"
    EBAY = "EBAY"


class Currency(str, Enum):
    """Supported currencies."""
    JPY = "JPY"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


# Normalized ranks for cross-marketplace comparison
# SNKRDUNK TCG: PSA10, A, B, C, D
# eBay Graded: Maps PSA 10 -> PSA10, PSA 9 -> A, PSA 7-8 -> B, etc.
# eBay Raw: Maps Near Mint -> A, Lightly Played -> B, etc.
NormalizedRank = Literal["PSA10", "A", "B", "C", "D"]

# TCG ranks we store (skip C, D for TCG)
TCG_RANKS_TO_STORE = {"PSA10", "A", "B"}


# ============================================================================
# DAILY AGGREGATION MODEL
# ============================================================================

class SoldItemDailyAgg(BaseModel):
    """
    Pre-computed daily aggregations for sold items.

    Stored in the 'sold_items_daily_agg' collection.

    Aggregates by: canonical_product_id + normalized_rank + source + sale_date

    This enables fast queries like:
    - "What's the average PSA10 price for pokemon-sv2a-165 over the last 30 days?"
    - "What's the price trend for this card on SNKRDUNK vs eBay?"

    Example Document:
        {
            "_id": "pokemon-sv2a-165_PSA10_SNKRDUNK_20240115",
            "canonical_product_id": "pokemon-sv2a-165",
            "normalized_rank": "PSA10",
            "source": "SNKRDUNK",
            "niche_type": "TCG",
            "sale_date": "2024-01-15",
            "min_price_jpy": 14000,
            "max_price_jpy": 16500,
            "avg_price_jpy": 15200.5,
            "sale_count": 5,
            "created_at": "2024-01-16T00:00:00Z",
            "scrape_session_id": "abc12345"
        }
    """
    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
    )

    # --- IDENTITY ---
    id: str = Field(
        ...,
        alias="_id",
        description="Compound key: {canonical_id}_{rank}_{source}_{YYYYMMDD}"
    )

    # --- DIMENSIONS ---
    canonical_product_id: str = Field(
        ...,
        description="Reference to canonical_products._id (e.g., 'pokemon-sv2a-165')"
    )

    normalized_rank: str = Field(
        ...,
        description="Normalized condition rank (PSA10, A, B, C, D)"
    )

    source: MarketplaceSource = Field(
        ...,
        description="Marketplace source (SNKRDUNK or EBAY)"
    )

    niche_type: Literal["TCG", "WATCH", "CAMERA_GEAR", "SNEAKER"] = Field(
        ...,
        description="Product niche type"
    )

    sale_date: date = Field(
        ...,
        description="Aggregation date (YYYY-MM-DD)"
    )

    # --- METRICS (JPY-normalized for comparison) ---
    min_price_jpy: int = Field(
        ...,
        ge=0,
        description="Minimum sale price in JPY"
    )

    max_price_jpy: int = Field(
        ...,
        ge=0,
        description="Maximum sale price in JPY"
    )

    avg_price_jpy: float = Field(
        ...,
        ge=0,
        description="Average sale price in JPY"
    )

    median_price_jpy: Optional[float] = Field(
        None,
        description="Median sale price in JPY (if calculable)"
    )

    sale_count: int = Field(
        ...,
        ge=1,
        description="Number of sales observed"
    )

    # --- ORIGINAL CURRENCY METRICS (for eBay with USD sales) ---
    avg_price_usd: Optional[float] = Field(
        None,
        description="Average price in USD (for eBay USD sales)"
    )

    # --- METADATA ---
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this aggregation was created"
    )

    scrape_session_id: Optional[str] = Field(
        None,
        description="Correlation ID for the scraping session"
    )

    def to_dict_for_db(self) -> dict:
        """Convert to dictionary for MongoDB insertion."""
        return self.model_dump(by_alias=True, mode='json')


# ============================================================================
# MONTHLY AGGREGATION MODEL
# ============================================================================

class SoldItemMonthlyAgg(BaseModel):
    """
    Pre-computed monthly aggregations for trend analysis.

    Stored in the 'sold_items_monthly_agg' collection.

    Aggregates by: canonical_product_id + normalized_rank + source + year_month

    Computed from daily aggregations for long-term trend analysis.

    Example Document:
        {
            "_id": "pokemon-sv2a-165_PSA10_SNKRDUNK_2024-01",
            "canonical_product_id": "pokemon-sv2a-165",
            "normalized_rank": "PSA10",
            "source": "SNKRDUNK",
            "niche_type": "TCG",
            "year_month": "2024-01",
            "min_price_jpy": 13500,
            "max_price_jpy": 17000,
            "avg_price_jpy": 15100.0,
            "total_sale_count": 120,
            "day_count": 28,
            "last_updated": "2024-02-01T00:00:00Z"
        }
    """
    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
    )

    # --- IDENTITY ---
    id: str = Field(
        ...,
        alias="_id",
        description="Compound key: {canonical_id}_{rank}_{source}_{YYYY-MM}"
    )

    # --- DIMENSIONS ---
    canonical_product_id: str = Field(
        ...,
        description="Reference to canonical_products._id"
    )

    normalized_rank: str = Field(
        ...,
        description="Normalized condition rank (PSA10, A, B, C, D)"
    )

    source: MarketplaceSource = Field(
        ...,
        description="Marketplace source"
    )

    niche_type: Literal["TCG", "WATCH", "CAMERA_GEAR", "SNEAKER"] = Field(
        ...,
        description="Product niche type"
    )

    year_month: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}$",
        description="Year-month in YYYY-MM format"
    )

    # --- METRICS ---
    min_price_jpy: int = Field(
        ...,
        ge=0,
        description="Minimum sale price in JPY for the month"
    )

    max_price_jpy: int = Field(
        ...,
        ge=0,
        description="Maximum sale price in JPY for the month"
    )

    avg_price_jpy: float = Field(
        ...,
        ge=0,
        description="Average sale price in JPY for the month"
    )

    median_price_jpy: Optional[float] = Field(
        None,
        description="Median sale price in JPY"
    )

    total_sale_count: int = Field(
        ...,
        ge=1,
        description="Total number of sales in the month"
    )

    day_count: int = Field(
        ...,
        ge=1,
        description="Number of days with sales data"
    )

    # --- TREND INDICATORS ---
    price_volatility: Optional[float] = Field(
        None,
        description="Standard deviation of daily average prices"
    )

    # --- ORIGINAL CURRENCY METRICS ---
    avg_price_usd: Optional[float] = Field(
        None,
        description="Average price in USD (for eBay)"
    )

    # --- METADATA ---
    last_updated: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last time this aggregation was updated"
    )

    def to_dict_for_db(self) -> dict:
        """Convert to dictionary for MongoDB insertion."""
        return self.model_dump(by_alias=True, mode='json')


# ============================================================================
# ID GENERATION FUNCTIONS
# ============================================================================

def generate_daily_agg_id(
    canonical_product_id: str,
    normalized_rank: str,
    source: MarketplaceSource,
    sale_date: date
) -> str:
    """
    Generate unique ID for daily aggregation.

    Format: {canonical_id}_{rank}_{source}_{YYYYMMDD}
    Example: pokemon-sv2a-165_PSA10_SNKRDUNK_20240115
    """
    date_str = sale_date.strftime("%Y%m%d")
    source_val = source.value if isinstance(source, MarketplaceSource) else source
    return f"{canonical_product_id}_{normalized_rank}_{source_val}_{date_str}"


def generate_monthly_agg_id(
    canonical_product_id: str,
    normalized_rank: str,
    source: MarketplaceSource,
    year_month: str
) -> str:
    """
    Generate unique ID for monthly aggregation.

    Format: {canonical_id}_{rank}_{source}_{YYYY-MM}
    Example: pokemon-sv2a-165_PSA10_SNKRDUNK_2024-01
    """
    source_val = source.value if isinstance(source, MarketplaceSource) else source
    return f"{canonical_product_id}_{normalized_rank}_{source_val}_{year_month}"


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================

def create_snkrdunk_daily_agg(
    canonical_product_id: str,
    niche_type: Literal["TCG", "WATCH", "CAMERA_GEAR", "SNEAKER"],
    rank: str,
    sale_date: date,
    min_price_jpy: int,
    max_price_jpy: int,
    avg_price_jpy: float,
    sale_count: int,
    median_price_jpy: Optional[float] = None,
    scrape_session_id: Optional[str] = None,
) -> SoldItemDailyAgg:
    """
    Factory function for creating SNKRDUNK daily aggregation records.

    Args:
        canonical_product_id: Reference to canonical_products._id
        niche_type: Product niche type
        rank: SNKRDUNK rank (PSA10, A, B, C, D for TCG)
        sale_date: Date of aggregation
        min_price_jpy: Minimum sale price
        max_price_jpy: Maximum sale price
        avg_price_jpy: Average sale price
        sale_count: Number of sales
        median_price_jpy: Median price (optional)
        scrape_session_id: Scraping session correlation ID

    Returns:
        SoldItemDailyAgg instance

    Example:
        agg = create_snkrdunk_daily_agg(
            canonical_product_id="pokemon-sv2a-165",
            niche_type="TCG",
            rank="PSA10",
            sale_date=date(2024, 1, 15),
            min_price_jpy=14000,
            max_price_jpy=16500,
            avg_price_jpy=15200.0,
            sale_count=5,
        )
    """
    normalized_rank = rank.upper().strip()

    agg_id = generate_daily_agg_id(
        canonical_product_id=canonical_product_id,
        normalized_rank=normalized_rank,
        source=MarketplaceSource.SNKRDUNK,
        sale_date=sale_date,
    )

    return SoldItemDailyAgg(
        _id=agg_id,
        canonical_product_id=canonical_product_id,
        normalized_rank=normalized_rank,
        source=MarketplaceSource.SNKRDUNK,
        niche_type=niche_type,
        sale_date=sale_date,
        min_price_jpy=min_price_jpy,
        max_price_jpy=max_price_jpy,
        avg_price_jpy=avg_price_jpy,
        median_price_jpy=median_price_jpy,
        sale_count=sale_count,
        avg_price_usd=None,
        scrape_session_id=scrape_session_id,
    )


def create_ebay_daily_agg(
    canonical_product_id: str,
    niche_type: Literal["TCG", "WATCH", "CAMERA_GEAR", "SNEAKER"],
    normalized_rank: str,
    sale_date: date,
    min_price_jpy: int,
    max_price_jpy: int,
    avg_price_jpy: float,
    sale_count: int,
    avg_price_usd: Optional[float] = None,
    median_price_jpy: Optional[float] = None,
    scrape_session_id: Optional[str] = None,
) -> SoldItemDailyAgg:
    """
    Factory function for creating eBay daily aggregation records.

    Args:
        canonical_product_id: Reference to canonical_products._id
        niche_type: Product niche type
        normalized_rank: Normalized rank (PSA10, A, B, C, D)
        sale_date: Date of aggregation
        min_price_jpy: Minimum sale price in JPY
        max_price_jpy: Maximum sale price in JPY
        avg_price_jpy: Average sale price in JPY
        sale_count: Number of sales
        avg_price_usd: Average price in USD (optional)
        median_price_jpy: Median price (optional)
        scrape_session_id: Scraping session correlation ID

    Returns:
        SoldItemDailyAgg instance

    Example:
        agg = create_ebay_daily_agg(
            canonical_product_id="pokemon-sv2a-165",
            niche_type="TCG",
            normalized_rank="PSA10",
            sale_date=date(2024, 1, 15),
            min_price_jpy=14500,
            max_price_jpy=16000,
            avg_price_jpy=15300.0,
            sale_count=8,
            avg_price_usd=102.0,
        )
    """
    normalized_rank = normalized_rank.upper().strip()

    agg_id = generate_daily_agg_id(
        canonical_product_id=canonical_product_id,
        normalized_rank=normalized_rank,
        source=MarketplaceSource.EBAY,
        sale_date=sale_date,
    )

    return SoldItemDailyAgg(
        _id=agg_id,
        canonical_product_id=canonical_product_id,
        normalized_rank=normalized_rank,
        source=MarketplaceSource.EBAY,
        niche_type=niche_type,
        sale_date=sale_date,
        min_price_jpy=min_price_jpy,
        max_price_jpy=max_price_jpy,
        avg_price_jpy=avg_price_jpy,
        median_price_jpy=median_price_jpy,
        sale_count=sale_count,
        avg_price_usd=avg_price_usd,
        scrape_session_id=scrape_session_id,
    )


def create_monthly_agg(
    canonical_product_id: str,
    niche_type: Literal["TCG", "WATCH", "CAMERA_GEAR", "SNEAKER"],
    normalized_rank: str,
    source: MarketplaceSource,
    year_month: str,
    min_price_jpy: int,
    max_price_jpy: int,
    avg_price_jpy: float,
    total_sale_count: int,
    day_count: int,
    median_price_jpy: Optional[float] = None,
    price_volatility: Optional[float] = None,
    avg_price_usd: Optional[float] = None,
) -> SoldItemMonthlyAgg:
    """
    Factory function for creating monthly aggregation records.

    Args:
        canonical_product_id: Reference to canonical_products._id
        niche_type: Product niche type
        normalized_rank: Normalized rank
        source: Marketplace source
        year_month: Year-month string (YYYY-MM)
        min_price_jpy: Minimum price for the month
        max_price_jpy: Maximum price for the month
        avg_price_jpy: Average price for the month
        total_sale_count: Total sales in the month
        day_count: Days with sales data
        median_price_jpy: Median price (optional)
        price_volatility: Standard deviation (optional)
        avg_price_usd: Average USD price (for eBay)

    Returns:
        SoldItemMonthlyAgg instance

    Example:
        agg = create_monthly_agg(
            canonical_product_id="pokemon-sv2a-165",
            niche_type="TCG",
            normalized_rank="PSA10",
            source=MarketplaceSource.SNKRDUNK,
            year_month="2024-01",
            min_price_jpy=13500,
            max_price_jpy=17000,
            avg_price_jpy=15100.0,
            total_sale_count=120,
            day_count=28,
        )
    """
    agg_id = generate_monthly_agg_id(
        canonical_product_id=canonical_product_id,
        normalized_rank=normalized_rank,
        source=source,
        year_month=year_month,
    )

    return SoldItemMonthlyAgg(
        _id=agg_id,
        canonical_product_id=canonical_product_id,
        normalized_rank=normalized_rank,
        source=source,
        niche_type=niche_type,
        year_month=year_month,
        min_price_jpy=min_price_jpy,
        max_price_jpy=max_price_jpy,
        avg_price_jpy=avg_price_jpy,
        median_price_jpy=median_price_jpy,
        total_sale_count=total_sale_count,
        day_count=day_count,
        price_volatility=price_volatility,
        avg_price_usd=avg_price_usd,
    )


# ============================================================================
# TYPE GUARDS
# ============================================================================

def is_snkrdunk_agg(agg: SoldItemDailyAgg) -> bool:
    """Check if aggregation is from SNKRDUNK."""
    return agg.source == MarketplaceSource.SNKRDUNK or agg.source == "SNKRDUNK"


def is_ebay_agg(agg: SoldItemDailyAgg) -> bool:
    """Check if aggregation is from eBay."""
    return agg.source == MarketplaceSource.EBAY or agg.source == "EBAY"


def should_store_tcg_rank(niche_type: str, rank: str) -> bool:
    """
    Determine if a TCG rank should be stored.

    TCG: Only store PSA10, A, B (skip C, D)
    Other niches: Store all ranks

    Args:
        niche_type: Product niche type
        rank: Normalized rank

    Returns:
        True if rank should be stored
    """
    if niche_type == "TCG":
        return rank.upper() in TCG_RANKS_TO_STORE
    return True


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

class CurrencyConverter:
    """
    Helper class for currency conversion.

    In production, this should fetch live rates from an API.
    For now, uses static rates that should be updated regularly.
    """

    # Static rates (should be updated via external service in production)
    RATES_TO_JPY: Dict[str, float] = {
        "JPY": 1.0,
        "USD": 150.0,  # Example: 1 USD = 150 JPY
        "EUR": 163.0,  # Example: 1 EUR = 163 JPY
        "GBP": 190.0,  # Example: 1 GBP = 190 JPY
    }

    @classmethod
    def to_jpy(cls, amount: float, currency: str) -> int:
        """
        Convert amount to JPY (rounded to nearest integer).

        Args:
            amount: Amount in original currency
            currency: Currency code (JPY, USD, EUR, GBP)

        Returns:
            Amount in JPY (rounded)
        """
        rate = cls.RATES_TO_JPY.get(currency, 150.0)
        return round(amount * rate)

    @classmethod
    def from_jpy(cls, amount_jpy: int, currency: str) -> float:
        """
        Convert JPY amount to target currency.

        Args:
            amount_jpy: Amount in JPY
            currency: Target currency code

        Returns:
            Amount in target currency (2 decimal places)
        """
        rate = cls.RATES_TO_JPY.get(currency, 150.0)
        return round(amount_jpy / rate, 2)


def normalize_ebay_grade_to_rank(grading_company: str, grade: float) -> str:
    """
    Normalize eBay graded card to standard rank.

    Maps PSA/BGS/CGC grades to SNKRDUNK-equivalent ranks:
    - 10.0: PSA10
    - 9.0-9.5: A
    - 7.0-8.5: B
    - 5.0-6.5: C
    - < 5.0: D

    Args:
        grading_company: PSA, BGS, CGC, etc.
        grade: Numeric grade (1-10)

    Returns:
        Normalized rank string
    """
    if grade >= 10.0:
        return "PSA10"
    elif grade >= 9.0:
        return "A"
    elif grade >= 7.0:
        return "B"
    elif grade >= 5.0:
        return "C"
    else:
        return "D"


def normalize_ebay_condition_to_rank(condition: str) -> str:
    """
    Normalize eBay raw card condition to standard rank.

    Maps text conditions to SNKRDUNK-equivalent ranks:
    - Near Mint: A
    - Lightly Played: B
    - Moderately Played: C
    - Heavily Played / Damaged: D

    Args:
        condition: eBay condition text

    Returns:
        Normalized rank string
    """
    condition_lower = condition.lower().strip()

    if "near mint" in condition_lower or "nm" in condition_lower:
        return "A"
    elif "lightly played" in condition_lower or "lp" in condition_lower:
        return "B"
    elif "moderately played" in condition_lower or "mp" in condition_lower:
        return "C"
    else:
        return "D"
