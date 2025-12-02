#!/usr/bin/env python3
"""
Pokemon Card Seeder - Scrapes pokemon-card.com using Playwright and seeds the database.

Usage:
    python main.py --sets sv2a sv4a
    python main.py --sets sv2a sv4a --headless  # Run in headless mode
"""
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import time
import uuid
from typing import List, Dict
from pydantic import ValidationError
from playwright.sync_api import sync_playwright, Page, Browser

from core.database import get_db, close_db
from core.models.product import create_pokemon_card_product
from core.logging import get_logger, log_execution_time

# Initialize logger for this service
logger = get_logger("seeder")


# Target URL
SEARCH_URL = "https://www.pokemon-card.com/card-search/"


@log_execution_time(logger)
def scrape_set_with_playwright(set_code: str, headless: bool = True) -> List[Dict]:
    """
    Scrapes pokemon-card.com for all cards in a specific set using Playwright.

    Args:
        set_code: The set code (e.g., 'sv2a')
        headless: Whether to run browser in headless mode

    Returns:
        List of card data dictionaries
    """
    correlation_id = str(uuid.uuid4())[:8]
    logger.info(
        f"Starting scrape for set: {set_code}",
        extra={"set_code": set_code, "correlation_id": correlation_id, "headless": headless}
    )

    cards_data = []

    try:
        with sync_playwright() as p:
            # Launch browser
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()

            # Navigate to search page
            logger.debug(f"Navigating to {SEARCH_URL}", extra={"correlation_id": correlation_id})
            page.goto(SEARCH_URL, wait_until='networkidle', timeout=60000)

            # Wait for page to load
            time.sleep(2)

            # Fill in the search form
            logger.debug(f"Searching for set: {set_code}", extra={"set_code": set_code, "correlation_id": correlation_id})

            # Find the keyword input field and enter the set code
            keyword_input = page.locator('input[name="keyword"]')
            if keyword_input.count() > 0:
                keyword_input.fill(set_code)
                logger.debug(f"Entered set code: {set_code}", extra={"correlation_id": correlation_id})
            else:
                logger.error("Could not find keyword input field", extra={"set_code": set_code, "correlation_id": correlation_id})
                browser.close()
                return []

            # Submit the form
            # Try to find and click the submit button
            submit_button = page.locator('button[type="submit"]').first
            if submit_button.count() == 0:
                # Try alternative selectors
                submit_button = page.locator('input[type="submit"]').first

            if submit_button.count() > 0:
                submit_button.click()
                logger.debug("Submitted search form", extra={"correlation_id": correlation_id})

                # Wait for results to load
                page.wait_for_load_state('networkidle', timeout=60000)
                time.sleep(3)
            else:
                logger.error("Could not find submit button", extra={"set_code": set_code, "correlation_id": correlation_id})
                browser.close()
                return []

            # Parse the results
            logger.info("Parsing card data...", extra={"correlation_id": correlation_id})

            # Try multiple possible selectors for card containers
            card_selectors = [
                '.card-list-item',
                '.CardlistBox',
                'section.Cards ul li',
                '.cardlist li',
                'ul.cardlist > li',
                '.Results ul li'
            ]

            card_elements = None
            for selector in card_selectors:
                elements = page.locator(selector)
                if elements.count() > 0:
                    card_elements = elements
                    logger.info(
                        f"Found {elements.count()} cards",
                        extra={"selector": selector, "count": elements.count(), "correlation_id": correlation_id}
                    )
                    break

            if not card_elements or card_elements.count() == 0:
                logger.warning(f"No card elements found for {set_code}", extra={"set_code": set_code, "correlation_id": correlation_id})
                screenshot_path = f"debug_{set_code}.png"
                page.screenshot(path=screenshot_path)
                logger.info(f"Screenshot saved for debugging", extra={"path": screenshot_path, "correlation_id": correlation_id})
                browser.close()
                return []

            # Extract data from each card
            total_cards = card_elements.count()
            logger.info(f"Extracting data from {total_cards} cards", extra={"total_cards": total_cards, "correlation_id": correlation_id})

            for idx in range(total_cards):
                try:
                    card_elem = card_elements.nth(idx)

                    # Extract card name (try multiple selectors)
                    name_jp = "Unknown Card"
                    for name_selector in ['.card-name', 'h3', '.name', '.cardName']:
                        name_elem = card_elem.locator(name_selector).first
                        if name_elem.count() > 0:
                            name_jp = name_elem.inner_text().strip()
                            break

                    # Extract card number
                    card_number = f"{idx + 1}"
                    for num_selector in ['.card-number', '.number', '.cardNumber']:
                        num_elem = card_elem.locator(num_selector).first
                        if num_elem.count() > 0:
                            card_number = num_elem.inner_text().strip()
                            break

                    # Extract rarity
                    rarity = "Unknown"
                    for rarity_selector in ['.rarity', '.card-rarity', '.cardRarity']:
                        rarity_elem = card_elem.locator(rarity_selector).first
                        if rarity_elem.count() > 0:
                            rarity = rarity_elem.inner_text().strip()
                            break

                    # Extract image URL
                    image_url = ""
                    img_elem = card_elem.locator('img').first
                    if img_elem.count() > 0:
                        img_src = img_elem.get_attribute('src')
                        if img_src:
                            if img_src.startswith('//'):
                                image_url = f"https:{img_src}"
                            elif img_src.startswith('/'):
                                image_url = f"https://www.pokemon-card.com{img_src}"
                            else:
                                image_url = img_src

                    # Extract source URL
                    source_url = SEARCH_URL
                    link_elem = card_elem.locator('a').first
                    if link_elem.count() > 0:
                        href = link_elem.get_attribute('href')
                        if href:
                            if href.startswith('//'):
                                source_url = f"https:{href}"
                            elif href.startswith('/'):
                                source_url = f"https://www.pokemon-card.com{href}"
                            elif href.startswith('http'):
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
                    logger.debug(f"Extracted card: {card_number} - {name_jp}", extra={"card_number": card_number, "correlation_id": correlation_id})

                except Exception as e:
                    logger.error(f"Failed to parse card {idx + 1}", exc_info=True, extra={"index": idx, "correlation_id": correlation_id})
                    continue

            logger.info(f"Successfully extracted {len(cards_data)} cards", extra={"cards_extracted": len(cards_data), "correlation_id": correlation_id})

            # Close browser
            browser.close()

    except Exception as e:
        logger.error("Playwright error occurred", exc_info=True, extra={"set_code": set_code, "correlation_id": correlation_id})
        return []

    return cards_data


@log_execution_time(logger)
def seed_database(cards_data: List[Dict]) -> int:
    """
    Validates and upserts card data into MongoDB.

    Args:
        cards_data: List of raw card data dictionaries

    Returns:
        Number of cards successfully inserted/updated
    """
    logger.info(f"Starting database seeding for {len(cards_data)} cards")
    db = get_db()
    collection = db["canonical_products"]
    success_count = 0
    error_count = 0

    for card in cards_data:
        try:
            # Build the canonical product using factory function
            # This automatically handles ID generation and proper identity structure
            product = create_pokemon_card_product(
                set_code=card["set_code"],
                card_number=card["card_number"],
                name_jp=card["name_jp"],
                rarity=card["rarity"],
                image_url=card["image_url"],
                source_url=card["source_url"],
            )

            # Convert to dict for MongoDB (use by_alias to get "_id")
            product_dict = product.model_dump(by_alias=True)

            # Upsert into database
            collection.update_one(
                {"_id": product.id},
                {"$set": product_dict},
                upsert=True
            )

            success_count += 1
            logger.debug(f"Upserted card: {product.id}", extra={"card_id": product.id, "name": card['name_jp']})

        except ValidationError as e:
            error_count += 1
            logger.error(f"Validation failed for card", exc_info=True, extra={"card": card.get('name_jp', 'Unknown')})
        except Exception as e:
            error_count += 1
            logger.error(f"Database error for card", exc_info=True, extra={"card": card.get('name_jp', 'Unknown')})

    logger.info(f"Database seeding completed", extra={"success": success_count, "errors": error_count, "total": len(cards_data)})
    return success_count


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Pokemon Card Database Seeder (Playwright)")
    parser.add_argument(
        "--sets",
        nargs="+",
        required=True,
        help="List of set codes to scrape (e.g., sv2a sv4a)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (no UI)"
    )

    args = parser.parse_args()

    # Log session start
    session_id = str(uuid.uuid4())[:8]
    logger.info("=" * 60)
    logger.info("VELODATA - POKEMON CARD SEEDER (PLAYWRIGHT)")
    logger.info("=" * 60)
    logger.info(
        "Starting seeder session",
        extra={
            "session_id": session_id,
            "sets": args.sets,
            "mode": "headless" if args.headless else "headed",
            "total_sets": len(args.sets)
        }
    )

    total_scraped = 0
    total_seeded = 0

    try:
        for set_code in args.sets:
            # Scrape the set with Playwright
            cards_data = scrape_set_with_playwright(set_code, headless=args.headless)
            total_scraped += len(cards_data)

            # Seed the database
            if cards_data:
                seeded = seed_database(cards_data)
                total_seeded += seeded
            else:
                logger.warning(f"No cards found for set: {set_code}", extra={"set_code": set_code, "session_id": session_id})

    except KeyboardInterrupt:
        logger.info("Seeding interrupted by user", extra={"session_id": session_id})
    except Exception as e:
        logger.critical("Fatal error occurred", exc_info=True, extra={"session_id": session_id})
    finally:
        close_db()

    # Log final summary
    logger.info("=" * 60)
    logger.info("SEEDER SESSION SUMMARY")
    logger.info("=" * 60)
    logger.info(
        "Session completed",
        extra={
            "session_id": session_id,
            "cards_scraped": total_scraped,
            "cards_seeded": total_seeded,
            "success_rate": f"{(total_seeded/total_scraped*100):.1f}%" if total_scraped > 0 else "N/A"
        }
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
