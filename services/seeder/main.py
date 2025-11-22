#!/usr/bin/env python3
"""
Pokemon Card Seeder - Scrapes pokemon-card.com and seeds the database.

Usage:
    python main.py --sets sv2a sv4a
"""
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from pydantic import ValidationError

from core.database import get_db, close_db
from core.models.product import CanonicalProduct, ProductIdentity, ProductMetadata


# Target URL
SEARCH_URL = "https://www.pokemon-card.com/card-search/index.php"


def scrape_set(set_code: str) -> List[Dict]:
    """
    Scrapes pokemon-card.com for all cards in a specific set.

    Args:
        set_code: The set code (e.g., 'sv2a')

    Returns:
        List of card data dictionaries
    """
    print(f"\n[SCRAPER] Fetching set: {set_code}")

    # Prepare the form data (mimics the search form)
    form_data = {
        "regulation_sidebar_form": "XY",
        "package": "",
        "regulation": "",
        "sm_and_xy_type": "",
        "keyword": set_code,
        "card_name": "",
        "seriesTitle": "",
    }

    try:
        # Send POST request
        response = requests.post(SEARCH_URL, data=form_data, timeout=30)
        response.raise_for_status()
        response.encoding = "utf-8"

        # Parse HTML
        soup = BeautifulSoup(response.text, "lxml")

        # Find all card items (adjust selector based on actual HTML structure)
        # This is a common pattern - cards are usually in a list/grid container
        cards_data = []

        # Try to find card containers - these are common selectors
        card_elements = soup.select(".card-list-item") or soup.select(".CardlistBox") or soup.select("section.Cards ul li")

        if not card_elements:
            print(f"[WARNING] No card elements found for {set_code}. Check the HTML structure.")
            return []

        print(f"[SCRAPER] Found {len(card_elements)} cards")

        for idx, card_elem in enumerate(card_elements, 1):
            try:
                # Extract card data (adjust selectors based on actual HTML)
                name_elem = card_elem.select_one(".card-name") or card_elem.select_one("h3") or card_elem.select_one(".name")
                number_elem = card_elem.select_one(".card-number") or card_elem.select_one(".number")
                rarity_elem = card_elem.select_one(".rarity") or card_elem.select_one(".card-rarity")
                image_elem = card_elem.select_one("img")

                # Get link to card detail page
                link_elem = card_elem.select_one("a")

                # Extract text and clean
                name_jp = name_elem.get_text(strip=True) if name_elem else f"Unknown Card {idx}"
                card_number = number_elem.get_text(strip=True) if number_elem else f"{idx}"
                rarity = rarity_elem.get_text(strip=True) if rarity_elem else "Unknown"

                # Get image URL
                image_url = ""
                if image_elem and image_elem.get("src"):
                    img_src = image_elem["src"]
                    # Handle relative URLs
                    if img_src.startswith("//"):
                        image_url = f"https:{img_src}"
                    elif img_src.startswith("/"):
                        image_url = f"https://www.pokemon-card.com{img_src}"
                    else:
                        image_url = img_src

                # Get source URL
                source_url = SEARCH_URL
                if link_elem and link_elem.get("href"):
                    href = link_elem["href"]
                    if href.startswith("//"):
                        source_url = f"https:{href}"
                    elif href.startswith("/"):
                        source_url = f"https://www.pokemon-card.com{href}"
                    elif href.startswith("http"):
                        source_url = href

                card_data = {
                    "set_code": set_code,
                    "card_number": card_number,
                    "name_jp": name_jp,
                    "rarity": rarity,
                    "image_url": image_url,
                    "source_url": source_url,
                }

                cards_data.append(card_data)

            except Exception as e:
                print(f"[ERROR] Failed to parse card {idx}: {e}")
                continue

        return cards_data

    except requests.RequestException as e:
        print(f"[ERROR] Network error while fetching {set_code}: {e}")
        return []
    except Exception as e:
        print(f"[ERROR] Unexpected error scraping {set_code}: {e}")
        return []


def seed_database(cards_data: List[Dict]) -> int:
    """
    Validates and upserts card data into MongoDB.

    Args:
        cards_data: List of raw card data dictionaries

    Returns:
        Number of cards successfully inserted/updated
    """
    db = get_db()
    collection = db["canonical_products"]
    success_count = 0

    for card in cards_data:
        try:
            # Generate unique ID
            card_id = f"{card['set_code']}-{card['card_number']}"

            # Build the canonical product
            product = CanonicalProduct(
                _id=card_id,
                niche_type="POKEMON_CARD",
                identity=ProductIdentity(
                    set_code=card["set_code"],
                    card_number=card["card_number"],
                    name_jp=card["name_jp"],
                    rarity=card["rarity"],
                ),
                metadata=ProductMetadata(
                    image_url=card["image_url"],
                    source_url=card["source_url"],
                ),
            )

            # Convert to dict for MongoDB (use by_alias to get "_id")
            product_dict = product.model_dump(by_alias=True)

            # Upsert into database
            collection.update_one(
                {"_id": card_id},
                {"$set": product_dict},
                upsert=True
            )

            success_count += 1
            print(f"[DB] Upserted: {card_id} - {card['name_jp']}")

        except ValidationError as e:
            print(f"[ERROR] Validation failed for {card.get('name_jp', 'Unknown')}: {e}")
        except Exception as e:
            print(f"[ERROR] Database error for {card.get('name_jp', 'Unknown')}: {e}")

    return success_count


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Pokemon Card Database Seeder")
    parser.add_argument(
        "--sets",
        nargs="+",
        required=True,
        help="List of set codes to scrape (e.g., sv2a sv4a)"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("VELODATA - POKEMON CARD SEEDER")
    print("=" * 60)
    print(f"Target sets: {', '.join(args.sets)}")

    total_scraped = 0
    total_seeded = 0

    try:
        for set_code in args.sets:
            # Scrape the set
            cards_data = scrape_set(set_code)
            total_scraped += len(cards_data)

            # Seed the database
            if cards_data:
                seeded = seed_database(cards_data)
                total_seeded += seeded
            else:
                print(f"[WARNING] No cards found for set: {set_code}")

    except KeyboardInterrupt:
        print("\n[INFO] Seeding interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Fatal error: {e}")
    finally:
        close_db()

    print("\n" + "=" * 60)
    print(f"SUMMARY")
    print("=" * 60)
    print(f"Cards scraped: {total_scraped}")
    print(f"Cards seeded:  {total_seeded}")
    print("=" * 60)


if __name__ == "__main__":
    main()
