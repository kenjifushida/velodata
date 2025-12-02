#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for polymorphic product models.
Validates that discriminated unions work correctly for different niche types.
"""
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.models.product import (
    CanonicalProduct,
    PokemonCardIdentity,
    WatchIdentity,
    CameraGearIdentity,
    ProductMetadata,
    create_pokemon_card_product,
    create_watch_product,
    create_camera_gear_product,
    is_pokemon_card,
    is_watch,
    is_camera_gear,
)
from pydantic import ValidationError


def test_pokemon_card_creation():
    """Test Pokemon card product creation with factory function."""
    print("\n=== Test 1: Pokemon Card Creation ===")

    product = create_pokemon_card_product(
        set_code="sv2a",
        card_number="165",
        name_jp="ԫ��ex",
        rarity="RR",
        image_url="https://example.com/image.jpg",
        source_url="https://pokemon-card.com/card/sv2a-165",
    )

    # Assertions
    assert product.id == "sv2a-165", f"Expected ID 'sv2a-165', got '{product.id}'"
    assert product.niche_type == "POKEMON_CARD", f"Expected niche 'POKEMON_CARD', got '{product.niche_type}'"
    assert isinstance(product.identity, PokemonCardIdentity), "Identity should be PokemonCardIdentity"
    assert product.identity.set_code == "sv2a"
    assert product.identity.card_number == "165"
    assert product.identity.name_jp == "ԫ��ex"
    assert is_pokemon_card(product), "Type guard should return True"

    print(" Pokemon card creation test passed")
    print(f"   Product ID: {product.id}")
    print(f"   Niche Type: {product.niche_type}")
    print(f"   Card: {product.identity.name_jp}")


def test_watch_creation():
    """Test watch product creation with factory function."""
    print("\n=== Test 2: Watch Creation ===")

    product = create_watch_product(
        brand="Rolex",
        model="Submariner",
        reference_number="126610LN",
        serial_number="ABC123XYZ",
        production_year=2023,
        image_url="https://example.com/rolex.jpg",
        source_url="https://chrono24.com/rolex/submariner",
    )

    # Assertions
    assert product.id == "rolex-ABC123XYZ", f"Expected ID 'rolex-ABC123XYZ', got '{product.id}'"
    assert product.niche_type == "WATCH", f"Expected niche 'WATCH', got '{product.niche_type}'"
    assert isinstance(product.identity, WatchIdentity), "Identity should be WatchIdentity"
    assert product.identity.brand == "Rolex"
    assert product.identity.model == "Submariner"
    assert product.identity.serial_number == "ABC123XYZ"
    assert is_watch(product), "Type guard should return True"

    print(" Watch creation test passed")
    print(f"   Product ID: {product.id}")
    print(f"   Niche Type: {product.niche_type}")
    print(f"   Watch: {product.identity.brand} {product.identity.model}")


def test_camera_gear_creation():
    """Test camera gear product creation with factory function."""
    print("\n=== Test 3: Camera Gear Creation ===")

    # Test Camera with condition
    camera_product = create_camera_gear_product(
        brand="Canon",
        model_number="EOS R5",
        subcategory="CAMERA",
        condition="New",
        image_url="https://example.com/eos-r5.jpg",
        source_url="https://bhphotovideo.com/canon-eos-r5",
    )

    # Assertions
    assert camera_product.id == "canon-camera-eos-r5", f"Expected ID 'canon-camera-eos-r5', got '{camera_product.id}'"
    assert camera_product.niche_type == "CAMERA_GEAR", f"Expected niche 'CAMERA_GEAR', got '{camera_product.niche_type}'"
    assert isinstance(camera_product.identity, CameraGearIdentity), "Identity should be CameraGearIdentity"
    assert camera_product.identity.brand == "Canon"
    assert camera_product.identity.model_number == "EOS R5"
    assert camera_product.identity.subcategory == "CAMERA"
    assert camera_product.identity.condition == "New"
    assert is_camera_gear(camera_product), "Type guard should return True"

    print("✓ Camera gear creation test passed (camera)")
    print(f"   Product ID: {camera_product.id}")
    print(f"   Niche Type: {camera_product.niche_type}")
    print(f"   Gear: {camera_product.identity.brand} {camera_product.identity.model_number}")

    # Test Lens with serial number
    lens_product = create_camera_gear_product(
        brand="Sony",
        model_number="FE 24-70mm f/2.8 GM II",
        subcategory="LENS",
        condition="Used - Excellent",
        serial_number="1234567",
        image_url="https://example.com/sony-lens.jpg",
        source_url="https://keh.com/sony-lens",
    )

    # Assertions for lens
    assert lens_product.id == "sony-1234567", f"Expected ID 'sony-1234567', got '{lens_product.id}'"
    assert lens_product.niche_type == "CAMERA_GEAR"
    assert isinstance(lens_product.identity, CameraGearIdentity)
    assert lens_product.identity.brand == "Sony"
    assert lens_product.identity.subcategory == "LENS"
    assert lens_product.identity.serial_number == "1234567"
    assert is_camera_gear(lens_product), "Type guard should return True"

    print("✓ Camera gear creation test passed (lens with serial)")
    print(f"   Product ID: {lens_product.id}")
    print(f"   Gear: {lens_product.identity.brand} {lens_product.identity.model_number}")


def test_manual_pokemon_card():
    """Test manual Pokemon card creation (without factory)."""
    print("\n=== Test 4: Manual Pokemon Card Creation ===")

    identity = PokemonCardIdentity(
        set_code="sv10",
        card_number="042",
        name_jp="����ex",
        rarity="SAR",
    )

    product = CanonicalProduct(
        _id=identity.generate_id(),
        identity=identity,
        metadata=ProductMetadata(
            image_url="https://example.com/charizard.jpg",
            source_url="https://pokemon-card.com",
        ),
    )

    assert product.id == "sv10-042"
    assert product.niche_type == "POKEMON_CARD"
    assert product.identity.rarity == "SAR"

    print(" Manual Pokemon card creation passed")


def test_wrong_niche_type_validation():
    """Test that wrong niche_type fails validation."""
    print("\n=== Test 5: Wrong Niche Type Validation ===")

    try:
        # Try to create a product with WATCH niche but Pokemon identity fields
        product = CanonicalProduct(
            _id="test-001",
            identity={
                "niche_type": "WATCH",  # Wrong!
                "set_code": "sv2a",  # This is Pokemon field
                "card_number": "001",
                "name_jp": "Test",
                "rarity": "R",
            },
            metadata=ProductMetadata(
                image_url="https://example.com/test.jpg",
                source_url="https://example.com",
            ),
        )
        print("L Should have raised ValidationError!")
        assert False, "Expected ValidationError but got none"

    except ValidationError as e:
        print(" Correctly raised ValidationError for mismatched niche type")
        print(f"   Error: {str(e)[:100]}...")


def test_serialization():
    """Test JSON serialization and deserialization."""
    print("\n=== Test 6: Serialization/Deserialization ===")

    # Create product
    product = create_pokemon_card_product(
        set_code="sv8",
        card_number="100",
        name_jp="����ex",
        rarity="UR",
        image_url="https://example.com/mewtwo.jpg",
        source_url="https://pokemon-card.com",
    )

    # Serialize to dict (for MongoDB)
    product_dict = product.model_dump(by_alias=True)

    assert "_id" in product_dict, "Should have _id field"
    assert "identity" in product_dict
    assert product_dict["identity"]["niche_type"] == "POKEMON_CARD"

    # Deserialize back
    restored_product = CanonicalProduct(**product_dict)

    assert restored_product.id == product.id
    assert restored_product.niche_type == product.niche_type
    assert isinstance(restored_product.identity, PokemonCardIdentity)

    print(" Serialization/deserialization test passed")
    print(f"   Original ID: {product.id}")
    print(f"   Restored ID: {restored_product.id}")


def test_type_guards():
    """Test type guard functions."""
    print("\n=== Test 7: Type Guards ===")

    pokemon_product = create_pokemon_card_product(
        set_code="sv1",
        card_number="001",
        name_jp="���",
        rarity="C",
        image_url="https://example.com/sprigatito.jpg",
        source_url="https://pokemon-card.com",
    )

    watch_product = create_watch_product(
        brand="Patek Philippe",
        model="Nautilus",
        reference_number="5711/1A",
        image_url="https://example.com/nautilus.jpg",
        source_url="https://chrono24.com",
    )

    # Pokemon product checks
    assert is_pokemon_card(pokemon_product), "Should identify as Pokemon card"
    assert not is_watch(pokemon_product), "Should not identify as watch"

    # Watch product checks
    assert is_watch(watch_product), "Should identify as watch"
    assert not is_pokemon_card(watch_product), "Should not identify as Pokemon card"

    print(" Type guards test passed")


def main():
    """Run all tests."""
    print("=" * 70)
    print("PRODUCT MODEL POLYMORPHISM TESTS")
    print("=" * 70)

    tests = [
        test_pokemon_card_creation,
        test_watch_creation,
        test_camera_gear_creation,
        test_manual_pokemon_card,
        test_wrong_niche_type_validation,
        test_serialization,
        test_type_guards,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"L Test failed: {test.__name__}")
            print(f"   Error: {e}")

    print("\n" + "=" * 70)
    print(f"SUMMARY: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
