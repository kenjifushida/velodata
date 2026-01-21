#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for sold item aggregation models.
Validates daily and monthly aggregation creation, serialization, and helpers.
"""
import sys
from pathlib import Path
from datetime import date, datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.models.sold_item import (
    # Enums
    MarketplaceSource,
    Currency,
    # Models
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
    TCG_RANKS_TO_STORE,
)


def test_snkrdunk_daily_agg_creation():
    """Test SNKRDUNK daily aggregation creation with factory function."""
    print("\n=== Test 1: SNKRDUNK Daily Aggregation Creation ===")

    agg = create_snkrdunk_daily_agg(
        canonical_product_id="pokemon-sv2a-165",
        niche_type="TCG",
        rank="PSA10",
        sale_date=date(2024, 1, 15),
        min_price_jpy=14000,
        max_price_jpy=16500,
        avg_price_jpy=15200.0,
        sale_count=5,
        median_price_jpy=15000.0,
        scrape_session_id="abc12345",
    )

    # Assertions
    assert agg.id == "pokemon-sv2a-165_PSA10_SNKRDUNK_20240115", f"Unexpected ID: {agg.id}"
    assert agg.canonical_product_id == "pokemon-sv2a-165"
    assert agg.normalized_rank == "PSA10"
    assert agg.source == MarketplaceSource.SNKRDUNK or agg.source == "SNKRDUNK"
    assert agg.niche_type == "TCG"
    assert agg.sale_date == date(2024, 1, 15)
    assert agg.min_price_jpy == 14000
    assert agg.max_price_jpy == 16500
    assert agg.avg_price_jpy == 15200.0
    assert agg.sale_count == 5
    assert agg.median_price_jpy == 15000.0
    assert agg.avg_price_usd is None  # SNKRDUNK is JPY only
    assert is_snkrdunk_agg(agg), "Type guard should return True"

    print("✓ SNKRDUNK daily aggregation creation test passed")
    print(f"   ID: {agg.id}")
    print(f"   Product: {agg.canonical_product_id}")
    print(f"   Rank: {agg.normalized_rank}")
    print(f"   Avg Price: ¥{agg.avg_price_jpy:,.0f}")
    print(f"   Sales: {agg.sale_count}")


def test_ebay_daily_agg_creation():
    """Test eBay daily aggregation creation with factory function."""
    print("\n=== Test 2: eBay Daily Aggregation Creation ===")

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
        median_price_jpy=15200.0,
        scrape_session_id="def67890",
    )

    # Assertions
    assert agg.id == "pokemon-sv2a-165_PSA10_EBAY_20240115", f"Unexpected ID: {agg.id}"
    assert agg.canonical_product_id == "pokemon-sv2a-165"
    assert agg.normalized_rank == "PSA10"
    assert agg.source == MarketplaceSource.EBAY or agg.source == "EBAY"
    assert agg.niche_type == "TCG"
    assert agg.sale_date == date(2024, 1, 15)
    assert agg.avg_price_jpy == 15300.0
    assert agg.avg_price_usd == 102.0
    assert agg.sale_count == 8
    assert is_ebay_agg(agg), "Type guard should return True"

    print("✓ eBay daily aggregation creation test passed")
    print(f"   ID: {agg.id}")
    print(f"   Product: {agg.canonical_product_id}")
    print(f"   Rank: {agg.normalized_rank}")
    print(f"   Avg Price: ¥{agg.avg_price_jpy:,.0f} (${agg.avg_price_usd})")
    print(f"   Sales: {agg.sale_count}")


def test_monthly_agg_creation():
    """Test monthly aggregation creation with factory function."""
    print("\n=== Test 3: Monthly Aggregation Creation ===")

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
        median_price_jpy=15000.0,
        price_volatility=850.0,
    )

    # Assertions
    assert agg.id == "pokemon-sv2a-165_PSA10_SNKRDUNK_2024-01", f"Unexpected ID: {agg.id}"
    assert agg.canonical_product_id == "pokemon-sv2a-165"
    assert agg.normalized_rank == "PSA10"
    assert agg.year_month == "2024-01"
    assert agg.total_sale_count == 120
    assert agg.day_count == 28
    assert agg.price_volatility == 850.0

    print("✓ Monthly aggregation creation test passed")
    print(f"   ID: {agg.id}")
    print(f"   Year-Month: {agg.year_month}")
    print(f"   Avg Price: ¥{agg.avg_price_jpy:,.0f}")
    print(f"   Total Sales: {agg.total_sale_count}")
    print(f"   Days with Data: {agg.day_count}")


def test_id_generation():
    """Test ID generation functions."""
    print("\n=== Test 4: ID Generation ===")

    # Daily agg ID
    daily_id = generate_daily_agg_id(
        canonical_product_id="pokemon-sv2a-165",
        normalized_rank="A",
        source=MarketplaceSource.EBAY,
        sale_date=date(2024, 3, 20),
    )
    assert daily_id == "pokemon-sv2a-165_A_EBAY_20240320", f"Unexpected daily ID: {daily_id}"
    print(f"✓ Daily ID: {daily_id}")

    # Monthly agg ID
    monthly_id = generate_monthly_agg_id(
        canonical_product_id="one_piece-OP01-001",
        normalized_rank="B",
        source=MarketplaceSource.SNKRDUNK,
        year_month="2024-02",
    )
    assert monthly_id == "one_piece-OP01-001_B_SNKRDUNK_2024-02", f"Unexpected monthly ID: {monthly_id}"
    print(f"✓ Monthly ID: {monthly_id}")


def test_tcg_rank_filtering():
    """Test TCG rank filtering logic."""
    print("\n=== Test 5: TCG Rank Filtering ===")

    # TCG should only store PSA10, A, B
    assert should_store_tcg_rank("TCG", "PSA10") is True
    assert should_store_tcg_rank("TCG", "A") is True
    assert should_store_tcg_rank("TCG", "B") is True
    assert should_store_tcg_rank("TCG", "C") is False
    assert should_store_tcg_rank("TCG", "D") is False

    # Other niches should store all ranks
    assert should_store_tcg_rank("WATCH", "C") is True
    assert should_store_tcg_rank("WATCH", "D") is True
    assert should_store_tcg_rank("SNEAKER", "D") is True

    # Verify constant
    assert TCG_RANKS_TO_STORE == {"PSA10", "A", "B"}

    print("✓ TCG rank filtering test passed")
    print(f"   TCG ranks to store: {TCG_RANKS_TO_STORE}")


def test_ebay_grade_normalization():
    """Test eBay grade to rank normalization."""
    print("\n=== Test 6: eBay Grade Normalization ===")

    # PSA/BGS grades to normalized ranks
    assert normalize_ebay_grade_to_rank("PSA", 10.0) == "PSA10"
    assert normalize_ebay_grade_to_rank("PSA", 9.5) == "A"
    assert normalize_ebay_grade_to_rank("PSA", 9.0) == "A"
    assert normalize_ebay_grade_to_rank("BGS", 8.5) == "B"
    assert normalize_ebay_grade_to_rank("BGS", 7.0) == "B"
    assert normalize_ebay_grade_to_rank("CGC", 6.0) == "C"
    assert normalize_ebay_grade_to_rank("PSA", 4.0) == "D"

    print("✓ eBay grade normalization test passed")
    print("   PSA 10 → PSA10")
    print("   PSA 9.5 → A")
    print("   BGS 8.5 → B")
    print("   CGC 6.0 → C")


def test_ebay_condition_normalization():
    """Test eBay text condition to rank normalization."""
    print("\n=== Test 7: eBay Condition Normalization ===")

    assert normalize_ebay_condition_to_rank("Near Mint") == "A"
    assert normalize_ebay_condition_to_rank("NM") == "A"
    assert normalize_ebay_condition_to_rank("Lightly Played") == "B"
    assert normalize_ebay_condition_to_rank("LP") == "B"
    assert normalize_ebay_condition_to_rank("Moderately Played") == "C"
    assert normalize_ebay_condition_to_rank("Heavily Played") == "D"
    assert normalize_ebay_condition_to_rank("Damaged") == "D"

    print("✓ eBay condition normalization test passed")
    print("   Near Mint → A")
    print("   Lightly Played → B")
    print("   Moderately Played → C")
    print("   Damaged → D")


def test_currency_conversion():
    """Test currency conversion helper."""
    print("\n=== Test 8: Currency Conversion ===")

    # USD to JPY (at rate of 150)
    jpy_amount = CurrencyConverter.to_jpy(100.0, "USD")
    assert jpy_amount == 15000, f"Expected 15000, got {jpy_amount}"
    print(f"✓ $100 USD → ¥{jpy_amount:,} JPY")

    # JPY to USD
    usd_amount = CurrencyConverter.from_jpy(15000, "USD")
    assert usd_amount == 100.0, f"Expected 100.0, got {usd_amount}"
    print(f"✓ ¥15,000 JPY → ${usd_amount} USD")

    # EUR to JPY (at rate of 163)
    jpy_from_eur = CurrencyConverter.to_jpy(100.0, "EUR")
    assert jpy_from_eur == 16300, f"Expected 16300, got {jpy_from_eur}"
    print(f"✓ €100 EUR → ¥{jpy_from_eur:,} JPY")

    # JPY stays as JPY
    jpy_same = CurrencyConverter.to_jpy(15000.0, "JPY")
    assert jpy_same == 15000, f"Expected 15000, got {jpy_same}"
    print("✓ JPY conversion identity check passed")


def test_serialization():
    """Test MongoDB serialization round-trip."""
    print("\n=== Test 9: MongoDB Serialization ===")

    # Create aggregation
    agg = create_snkrdunk_daily_agg(
        canonical_product_id="pokemon-sv2a-165",
        niche_type="TCG",
        rank="A",
        sale_date=date(2024, 1, 15),
        min_price_jpy=8000,
        max_price_jpy=12000,
        avg_price_jpy=10000.0,
        sale_count=15,
    )

    # Serialize to dict
    doc = agg.to_dict_for_db()

    # Assertions
    assert doc["_id"] == "pokemon-sv2a-165_A_SNKRDUNK_20240115"
    assert doc["canonical_product_id"] == "pokemon-sv2a-165"
    assert doc["normalized_rank"] == "A"
    assert doc["source"] == "SNKRDUNK"
    assert doc["niche_type"] == "TCG"
    assert doc["min_price_jpy"] == 8000
    assert doc["max_price_jpy"] == 12000
    assert doc["avg_price_jpy"] == 10000.0
    assert doc["sale_count"] == 15
    assert "created_at" in doc

    # Deserialize back
    restored = SoldItemDailyAgg(**doc)
    assert restored.id == agg.id
    assert restored.canonical_product_id == agg.canonical_product_id
    assert restored.normalized_rank == agg.normalized_rank

    print("✓ Serialization round-trip test passed")
    print(f"   Document _id: {doc['_id']}")


def test_type_guards():
    """Test type guard functions."""
    print("\n=== Test 10: Type Guards ===")

    snkrdunk_agg = create_snkrdunk_daily_agg(
        canonical_product_id="pokemon-sv2a-165",
        niche_type="TCG",
        rank="PSA10",
        sale_date=date(2024, 1, 15),
        min_price_jpy=14000,
        max_price_jpy=16000,
        avg_price_jpy=15000.0,
        sale_count=5,
    )

    ebay_agg = create_ebay_daily_agg(
        canonical_product_id="pokemon-sv2a-165",
        niche_type="TCG",
        normalized_rank="PSA10",
        sale_date=date(2024, 1, 15),
        min_price_jpy=14000,
        max_price_jpy=16000,
        avg_price_jpy=15000.0,
        sale_count=5,
    )

    # Test SNKRDUNK guards
    assert is_snkrdunk_agg(snkrdunk_agg) is True
    assert is_ebay_agg(snkrdunk_agg) is False

    # Test eBay guards
    assert is_snkrdunk_agg(ebay_agg) is False
    assert is_ebay_agg(ebay_agg) is True

    print("✓ Type guard test passed")
    print("   is_snkrdunk_agg(snkrdunk_agg) = True")
    print("   is_ebay_agg(ebay_agg) = True")


def main():
    """Run all tests."""
    print("=" * 60)
    print("SOLD ITEM AGGREGATION MODEL TESTS")
    print("=" * 60)

    tests = [
        test_snkrdunk_daily_agg_creation,
        test_ebay_daily_agg_creation,
        test_monthly_agg_creation,
        test_id_generation,
        test_tcg_rank_filtering,
        test_ebay_grade_normalization,
        test_ebay_condition_normalization,
        test_currency_conversion,
        test_serialization,
        test_type_guards,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"\n❌ FAILED: {test.__name__}")
            print(f"   Error: {e}")
        except Exception as e:
            failed += 1
            print(f"\n❌ ERROR: {test.__name__}")
            print(f"   Exception: {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())
