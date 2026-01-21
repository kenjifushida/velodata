"""
VeloData Core Models

Exports for product, market listing, and sold item aggregation models.
"""

# Product models (canonical golden records)
from core.models.product import (
    # Identity models
    TCGIdentity,
    WatchIdentity,
    CameraGearIdentity,
    ProductIdentity,
    # Main model
    CanonicalProduct,
    ProductMetadata,
    # Factory functions
    create_tcg_product,
    create_watch_product,
    create_camera_gear_product,
    # Type guards
    is_tcg,
    is_tcg_game,
    is_watch,
    is_camera_gear,
)

# Market listing models (raw scraped data)
from core.models.market_listing import (
    # Source and enums
    MarketSource,
    ConditionRank,
    # Main model
    MarketListing,
    # Factory functions
    create_hardoff_listing,
    create_mercari_listing,
    create_suruga_ya_listing,
    create_map_camera_listing,
    create_paypay_listing,
    # Attribute helpers
    CameraGearAttributes,
    WatchAttributes,
    TCGAttributes,
    # Validation helpers
    validate_condition_rank,
    normalize_condition_rank,
)

# Sold item aggregation models (price data from SNKRDUNK/eBay)
from core.models.sold_item import (
    # Enums
    MarketplaceSource,
    Currency,
    # Main models
    SoldItemDailyAgg,
    SoldItemMonthlyAgg,
    # Factory functions
    create_snkrdunk_daily_agg,
    create_ebay_daily_agg,
    create_monthly_agg,
    # ID generation
    generate_daily_agg_id,
    generate_monthly_agg_id,
    # Type guards
    is_snkrdunk_agg,
    is_ebay_agg,
    should_store_tcg_rank,
    # Helpers
    CurrencyConverter,
    normalize_ebay_grade_to_rank,
    normalize_ebay_condition_to_rank,
    # Constants
    TCG_RANKS_TO_STORE,
)

__all__ = [
    # Product models
    "TCGIdentity",
    "WatchIdentity",
    "CameraGearIdentity",
    "ProductIdentity",
    "CanonicalProduct",
    "ProductMetadata",
    "create_tcg_product",
    "create_watch_product",
    "create_camera_gear_product",
    "is_tcg",
    "is_tcg_game",
    "is_watch",
    "is_camera_gear",
    # Market listing models
    "MarketSource",
    "ConditionRank",
    "MarketListing",
    "create_hardoff_listing",
    "create_mercari_listing",
    "create_suruga_ya_listing",
    "create_map_camera_listing",
    "create_paypay_listing",
    "CameraGearAttributes",
    "WatchAttributes",
    "TCGAttributes",
    "validate_condition_rank",
    "normalize_condition_rank",
    # Sold item aggregation models
    "MarketplaceSource",
    "Currency",
    "SoldItemDailyAgg",
    "SoldItemMonthlyAgg",
    "create_snkrdunk_daily_agg",
    "create_ebay_daily_agg",
    "create_monthly_agg",
    "generate_daily_agg_id",
    "generate_monthly_agg_id",
    "is_snkrdunk_agg",
    "is_ebay_agg",
    "should_store_tcg_rank",
    "CurrencyConverter",
    "normalize_ebay_grade_to_rank",
    "normalize_ebay_condition_to_rank",
    "TCG_RANKS_TO_STORE",
]
