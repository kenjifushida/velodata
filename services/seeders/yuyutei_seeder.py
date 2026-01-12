"""
Yuyutei Multi-TCG Card Seeder

Scrapes TCG canonical products from Yuyutei (yuyu-tei.jp) for multiple games:
- Pokemon
- Yu-Gi-Oh!
- One Piece
- Magic: The Gathering

Seeds them into the canonical_products collection as the golden record.

Usage:
    # One Piece - Dry run (no database writes, see browser)
    python services/seeders/yuyutei_seeder.py --game ONE_PIECE --sets OP01 --max-pages 1 --dry-run --headed

    # Pokemon - Live run
    python services/seeders/yuyutei_seeder.py --game POKEMON --sets SV2a SV4a --max-pages 10

    # Yu-Gi-Oh! - All sets
    python services/seeders/yuyutei_seeder.py --game YUGIOH --all-sets --max-pages 20

    # Magic - With rarity filter
    python services/seeders/yuyutei_seeder.py --game MAGIC --sets BRO --rarities M R --max-pages 5
"""

import argparse
import re
import sys
import time
import random
import uuid
from typing import Dict, List, Optional, Literal
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from pydantic import ValidationError

from core.models.product import create_tcg_product
from core.database import get_db, close_db
from core.logging import get_logger, log_execution_time

# Initialize logger
logger = get_logger("yuyutei-seeder")


# ============================================================================
# PLAYWRIGHT STEALTH CONFIGURATION
# ============================================================================

def create_stealth_context(browser: Browser) -> BrowserContext:
    """
    Create a stealth browser context with anti-bot measures.

    Based on PayPay scraper stealth techniques for Japanese sites.

    Args:
        browser: Playwright browser instance

    Returns:
        BrowserContext configured with stealth settings
    """
    # Randomize viewport to appear more human-like
    viewport_width = random.randint(1366, 1920)
    viewport_height = random.randint(768, 1080)

    logger.debug(
        "Creating stealth context",
        extra={
            "viewport_width": viewport_width,
            "viewport_height": viewport_height
        }
    )

    # Create context with stealth settings
    context = browser.new_context(
        viewport={'width': viewport_width, 'height': viewport_height},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        locale='ja-JP',
        timezone_id='Asia/Tokyo',
    )

    # Override navigator.webdriver to hide automation
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)

    return context


def simulate_human_behavior(page: Page):
    """
    Simulate human-like behavior on the page (mouse movements, scrolling).

    Args:
        page: Playwright page instance
    """
    try:
        # Random mouse movements (2-4 movements)
        num_movements = random.randint(2, 4)
        for _ in range(num_movements):
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            page.mouse.move(x, y)
            time.sleep(random.uniform(0.1, 0.3))

        # Simulate scrolling (incremental scroll down)
        scroll_amount = 0
        max_scroll = random.randint(1000, 2000)

        while scroll_amount < max_scroll:
            scroll_step = random.randint(200, 500)
            page.evaluate(f"window.scrollBy(0, {scroll_step})")
            scroll_amount += scroll_step
            time.sleep(random.uniform(0.3, 0.8))

        # Scroll to top
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(random.uniform(0.5, 1.0))

        logger.debug("Human behavior simulation complete")

    except Exception as e:
        logger.warning(f"Failed to simulate human behavior: {e}")

# TCG Game Type
TCGGame = Literal["POKEMON", "YUGIOH", "ONE_PIECE", "MAGIC"]

# Game-specific configuration
GAME_CONFIG = {
    "POKEMON": {
        "url_slug": "poke",
        "search_url": "https://yuyu-tei.jp/sell/poke/s/search",
        "set_pattern": r'\b([A-Z]{1,2}\d{1,2}[a-z]?)\b',  # SV2a, S12a, etc.
        "card_pattern": r'([A-Z]{1,2}\d{1,2}[a-z]?)-(\d{3})',  # Without brackets for img alt
    },
    "YUGIOH": {
        "url_slug": "yugi",
        "search_url": "https://yuyu-tei.jp/sell/yugi/s/search",
        "set_pattern": r'\b([A-Z]{2,4}-[A-Z]{2}\d{3})\b',  # DBAD-JP001, etc.
        "card_pattern": r'([A-Z]{2,4}-[A-Z]{2}\d{3})',  # Without brackets for img alt
    },
    "ONE_PIECE": {
        "url_slug": "opc",
        "search_url": "https://yuyu-tei.jp/sell/opc/s/search",
        "set_pattern": r'\b([A-Z]{2}\d{2})\b',  # OP01, ST01, etc.
        "card_pattern": r'([A-Z]{2}\d{2})-(\d{3})',  # Without brackets - matches "OP01-120"
    },
    "MAGIC": {
        "url_slug": "mtg",
        "search_url": "https://yuyu-tei.jp/sell/mtg/s/search",
        "set_pattern": r'\b([A-Z]{3})\b',  # BRO, ONE, MOM, etc.
        "card_pattern": r'([A-Z]{3})-(\d{3})',  # Without brackets for img alt
    }
}

YUYUTEI_BASE_URL = "https://yuyu-tei.jp"


@log_execution_time(logger)
def discover_and_map_sets(page: Page, game: TCGGame) -> Dict[str, str]:
    """
    Dynamically discover Yuyutei's internal set code mapping for a specific game.

    Yuyutei uses internal codes (e.g., "4010" for OP01) in form values.
    This function scrapes the search form to build the mapping.

    Strategy:
    1. Navigate to game-specific search page
    2. Find all vers[] checkboxes
    3. Extract label text (e.g., "OP01 ROMANCE DAWN")
    4. Extract value attribute (e.g., "4010")
    5. Parse label to get set code → Build mapping

    Args:
        page: Playwright Page object
        game: TCG game name (POKEMON, YUGIOH, ONE_PIECE, MAGIC)

    Returns:
        Dict mapping public set codes to internal codes
        Example: {"OP01": "4010", "OP02": "4020", "ST01": "8010"}
    """
    config = GAME_CONFIG[game]
    logger.info(f"Discovering set code mapping for {game} from Yuyutei")

    try:
        # Use longer timeout and load wait strategy
        page.goto(config["search_url"], wait_until="load", timeout=60000)
        time.sleep(2)  # Allow JS to initialize

        # Simulate human behavior to avoid bot detection
        simulate_human_behavior(page)

        mapping = {}
        set_checkboxes = page.locator('input[name="vers[]"]')
        checkbox_count = set_checkboxes.count()

        logger.debug(f"Found {checkbox_count} set checkboxes for {game}")

        for i in range(checkbox_count):
            try:
                checkbox = set_checkboxes.nth(i)
                internal_code = checkbox.get_attribute("value")

                if not internal_code:
                    continue

                # Find associated label
                label_text = None

                # Strategy 1: Label with for attribute
                label_locator = page.locator(f'label[for*="{internal_code}"]')
                if label_locator.count() > 0:
                    label_text = label_locator.first.inner_text()

                # Strategy 2: Parent label
                if not label_text:
                    parent = checkbox.locator('..')
                    if parent.count() > 0:
                        label_text = parent.inner_text()

                if label_text:
                    # Parse set code from label using game-specific pattern
                    set_match = re.search(config["set_pattern"], label_text)
                    if set_match:
                        set_code = set_match.group(1)  # e.g., "OP01", "ST01", "EB01"

                        # Verify internal_code matches the set_code from label
                        # internal_code should be the lowercase version of set_code
                        # e.g., "op01" for OP01, "st01" for ST01, "promo-op10" for PROMO sets
                        if internal_code and internal_code.lower() == set_code.lower():
                            # Direct match - this is the correct mapping
                            mapping[set_code.upper()] = internal_code.lower()
                            logger.debug(f"Mapped {set_code.upper()} → {internal_code.lower()} (label: {label_text})")
                        elif internal_code and set_code.lower() in internal_code.lower():
                            # Partial match - could be promo set like "promo-op10"
                            # Only map if it's an exact substring match at the end
                            if internal_code.lower().endswith(set_code.lower()):
                                mapping[set_code.upper()] = internal_code.lower()
                                logger.debug(f"Mapped {set_code.upper()} → {internal_code.lower()} (promo/special, label: {label_text})")
                            else:
                                logger.debug(f"Skipping partial match: {set_code} in {internal_code} (label: {label_text})")
                        else:
                            logger.debug(f"No match between set_code={set_code} and internal_code={internal_code} (label: {label_text})")

            except Exception as e:
                logger.warning(f"Failed to process checkbox {i}", exc_info=True)
                continue

        logger.info(f"Successfully discovered {len(mapping)} set code mappings for {game}")
        return mapping

    except Exception as e:
        logger.error(f"Failed to discover set code mapping for {game}", exc_info=True)
        raise


def build_search_url(
    game: TCGGame,
    set_codes: List[str],
    set_code_map: Dict[str, str],
    rarities: Optional[List[str]] = None
) -> str:
    """
    Build Yuyutei search URL with query parameters.

    More reliable than form submission - constructs URL directly.

    Args:
        game: TCG game name
        set_codes: List of public set codes (e.g., ["OP01", "OP14"])
        set_code_map: Mapping from public to internal codes
        rarities: Optional list of rarities to filter

    Returns:
        Complete search URL with parameters
    """
    config = GAME_CONFIG[game]
    base_url = config["search_url"]

    # Build query parameters
    params = []
    params.append("search_word=")  # Empty search word

    # Add set codes (vers[])
    for set_code in set_codes:
        internal_code = set_code_map.get(set_code)
        if internal_code:
            # URL encode: vers[] becomes vers%5B%5D
            params.append(f"vers%5B%5D={internal_code}")
            logger.debug(f"Added set to URL: {set_code} → {internal_code}")
        else:
            logger.warning(f"Set code {set_code} not found in mapping")

    # Add rarities (rare[])
    if rarities:
        for rarity in rarities:
            params.append(f"rare={rarity}")
            logger.debug(f"Added rarity to URL: {rarity}")

    # Build full URL
    full_url = f"{base_url}?{'&'.join(params)}"
    logger.info(f"Built search URL for {game}: {full_url[:100]}...")

    return full_url


@log_execution_time(logger)
def navigate_to_search_results(
    page: Page,
    game: TCGGame,
    set_codes: List[str],
    set_code_map: Dict[str, str],
    rarities: Optional[List[str]] = None
) -> None:
    """
    Navigate directly to search results using URL construction.

    More reliable than form submission - bypasses JavaScript form handlers.

    Args:
        page: Playwright Page object
        game: TCG game name
        set_codes: List of public set codes (e.g., ["OP01", "OP14"])
        set_code_map: Mapping from public to internal codes
        rarities: Optional list of rarities to filter
    """
    logger.info(f"Navigating to search results for {game}: sets={set_codes}, rarities={rarities}")

    try:
        # Build search URL with parameters
        search_url = build_search_url(game, set_codes, set_code_map, rarities)

        # Navigate directly to results
        page.goto(search_url, wait_until="load", timeout=60000)
        time.sleep(3)  # Allow JS to initialize and load cards

        # Wait for cards to appear (try multiple selectors)
        try:
            page.wait_for_selector('.card_unit, .itemlistbox, li', timeout=10000)
            logger.debug("Card elements loaded")
        except Exception as e:
            logger.warning(f"Timeout waiting for card elements: {e}")

        # Simulate human behavior
        simulate_human_behavior(page)

        logger.info(f"Successfully navigated to search results for {game}")

    except Exception as e:
        logger.error(f"Failed to navigate to search results for {game}", exc_info=True)
        raise


def extract_card_data_from_page(page: Page, game: TCGGame) -> List[Dict]:
    """
    Extract card data from search results page for a specific game.

    Uses multiple selector fallbacks for robustness against HTML structure changes.
    Applies game-specific regex patterns for card code extraction.

    Expected card format: [OP12-014] SR ボア・ハンコック 220 円

    Args:
        page: Playwright Page object
        game: TCG game name

    Returns:
        List of card data dictionaries with keys:
        - set_code: str (e.g., "OP12" or "SV2a")
        - card_number: str (e.g., "014")
        - name_jp: str | None (e.g., "ボア・ハンコック")
        - rarity: str | None (e.g., "SR")
        - price_jpy: int | None (e.g., 220)
        - image_url: str (required)
        - source_url: str (required)
    """
    config = GAME_CONFIG[game]
    cards = []

    # Multiple selector fallbacks
    # Yuyutei uses card-product class for individual cards (confirmed from HTML inspection)
    selectors = [
        '.card-product',          # Yuyutei's actual card container (primary)
        '.card_unit',             # Yuyutei's alternative card container
        '.itemlistbox',           # Primary container
        '.product-item',          # Alternative
        'ul.card-list > li',      # List layout
        'table.card-table tr',    # Table layout
        '.card-item',             # Generic card item
        '[data-card-id]',         # Data attribute
    ]

    card_elements = None
    used_selector = None

    for selector in selectors:
        elements = page.locator(selector)
        if elements.count() > 0:
            card_elements = elements
            used_selector = selector
            logger.debug(f"Using selector: {selector} (found {elements.count()} elements)")
            break

    if not card_elements or card_elements.count() == 0:
        logger.warning(f"No card elements found for {game} with any selector")

        # Take debug screenshot and save HTML
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"debug_yuyutei_{game.lower()}_{timestamp}.png"
        html_path = f"debug_yuyutei_{game.lower()}_{timestamp}.html"

        try:
            page.screenshot(path=screenshot_path)
            logger.warning(f"Debug screenshot saved: {screenshot_path}")
        except Exception as e:
            logger.error(f"Failed to save debug screenshot: {e}")

        try:
            html_content = page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.warning(f"Debug HTML saved: {html_path}")
        except Exception as e:
            logger.error(f"Failed to save debug HTML: {e}")

        return []

    element_count = card_elements.count()
    logger.info(f"Found {element_count} card elements for {game}")

    for i in range(element_count):
        try:
            card_elem = card_elements.nth(i)

            # Extract card info from img alt attribute
            # Format: "OP01-120 P-SEC シャンクス(パラレル)"
            img_elem = card_elem.locator('img.card')  # Yuyutei uses img with class="card"
            if img_elem.count() == 0:
                logger.warning(f"Skipping element {i}: No image with class='card' found")
                continue

            img_alt = img_elem.get_attribute('alt')
            if not img_alt:
                logger.warning(f"Skipping element {i}: No alt text on image")
                continue

            logger.debug(f"Processing card {i}: alt='{img_alt}'")

            # Extract card code using game-specific pattern from alt text
            code_match = re.search(config["card_pattern"], img_alt)
            if not code_match:
                logger.warning(f"Skipping element {i}: No card code found in alt text: {img_alt}")
                continue

            # For games with set-card format (Pokemon, One Piece, Magic)
            if len(code_match.groups()) >= 2:
                set_code = code_match.group(1)
                card_number = code_match.group(2)
            else:
                # For Yu-Gi-Oh! with single code format
                full_code = code_match.group(1)
                # Parse DBAD-JP001 → set_code="DBAD-JP", card_number="001"
                yugioh_match = re.match(r'([A-Z]{2,4}-[A-Z]{2})(\d{3})', full_code)
                if yugioh_match:
                    set_code = yugioh_match.group(1)
                    card_number = yugioh_match.group(2)
                else:
                    set_code = full_code
                    card_number = "000"

            # Extract rarity from alt text (game-agnostic)
            rarity_match = re.search(r'(P-SEC|SEC|P-SR|SR|R|UC|C|RR|RRR|UR|M|MR)', img_alt)
            rarity = rarity_match.group(1) if rarity_match else None

            # Extract name from alt text
            # Pattern: After card code and rarity, get the Japanese name
            # Example: "OP01-120 P-SEC シャンクス(パラレル)" → "シャンクス(パラレル)"
            name_jp = None
            if rarity:
                # Remove card code and rarity from alt text to get name
                name_part = img_alt.replace(f"{set_code}-{card_number}", "").replace(rarity, "").strip()
                name_jp = name_part if name_part else None

            # Get text content for price extraction
            text = card_elem.inner_text()

            # Extract price
            price_jpy = None
            price_match = re.search(r'(\d+(?:,\d+)*)\s*円', text)
            if price_match:
                price_str = price_match.group(1).replace(',', '')
                try:
                    price_jpy = int(price_str)
                except ValueError:
                    logger.warning(f"Invalid price format: {price_str}")

            # Extract image URL (we already have img_elem from earlier)
            image_url = None
            img_src = img_elem.get_attribute('src')
            if img_src and not img_src.startswith('data:'):
                # Handle relative URLs
                if img_src.startswith('http'):
                    image_url = img_src
                elif img_src.startswith('//'):
                    image_url = f"https:{img_src}"
                else:
                    image_url = f"{YUYUTEI_BASE_URL}{img_src}"

            # Extract source URL (detail page)
            link_elem = card_elem.locator('a').first
            source_url = config["search_url"]  # Default fallback
            if link_elem.count() > 0:
                href = link_elem.get_attribute('href')
                if href:
                    if href.startswith('http'):
                        source_url = href
                    elif href.startswith('//'):
                        source_url = f"https:{href}"
                    else:
                        source_url = f"{YUYUTEI_BASE_URL}{href}"

            # Required fields check
            if not image_url:
                logger.warning(f"Skipping card {set_code}-{card_number}: No image URL")
                continue

            card_data = {
                "set_code": set_code,
                "card_number": card_number,
                "name_jp": name_jp,
                "rarity": rarity,
                "price_jpy": price_jpy,
                "image_url": image_url,
                "source_url": source_url
            }

            cards.append(card_data)
            logger.debug(f"Extracted: {set_code}-{card_number} {name_jp} ({rarity})")

        except Exception as e:
            logger.error(f"Failed to extract card {i}", exc_info=True)
            continue

    logger.info(f"Successfully extracted {len(cards)} cards for {game} from page")
    return cards


def scrape_all_pages(page: Page, game: TCGGame, max_pages: int) -> List[Dict]:
    """
    Scrape all result pages up to max_pages for a specific game.

    Handles pagination by clicking "next" button and extracting cards from each page.

    Args:
        page: Playwright Page object
        game: TCG game name
        max_pages: Maximum number of pages to scrape

    Returns:
        List of all card data dictionaries from all pages
    """
    all_cards = []
    current_page = 1

    while current_page <= max_pages:
        logger.info(f"Scraping page {current_page}/{max_pages} for {game}")

        # Extract cards from current page
        try:
            cards = extract_card_data_from_page(page, game)
            all_cards.extend(cards)
            logger.info(f"Found {len(cards)} cards on page {current_page}")
        except Exception as e:
            logger.error(f"Failed to extract cards from page {current_page}", exc_info=True)

        # Check if we should continue
        if current_page >= max_pages:
            logger.info(f"Reached max pages limit ({max_pages})")
            break

        # Check for next page button
        next_selectors = [
            'a.next-page',
            'a[rel="next"]',
            '.pagination .next',
            'a:has-text("次へ")',  # "Next" in Japanese
            'a:has-text("＞")',    # > symbol
            '.pagination a:last-child',
        ]

        next_button = None
        for selector in next_selectors:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible():
                    next_button = btn
                    logger.debug(f"Found next button with selector: {selector}")
                    break
            except Exception:
                continue

        if not next_button:
            logger.info("No more pages available (no next button found)")
            break

        # Click next page
        try:
            logger.debug("Clicking next page button")
            next_button.click()
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(random.uniform(2, 4))  # Rate limiting + JS rendering
            current_page += 1
        except Exception as e:
            logger.error("Failed to navigate to next page", exc_info=True)
            break

    logger.info(f"Scraped {len(all_cards)} total cards for {game} across {current_page} pages")
    return all_cards


@log_execution_time(logger)
def seed_canonical_products(
    game: TCGGame,
    cards_data: List[Dict],
    dry_run: bool = False,
    session_id: Optional[str] = None
) -> Dict[str, int]:
    """
    Validate and upsert cards into canonical_products collection.

    Uses create_tcg_product() factory for validation and ID generation.
    Logs prices as metadata (not stored in canonical product).

    Args:
        game: TCG game name
        cards_data: List of card data dictionaries
        dry_run: If True, only validate without database writes
        session_id: Optional correlation ID for logging

    Returns:
        Dict with stats: {"inserted": N, "updated": M, "errors": K}
    """
    logger.info(
        f"Seeding {len(cards_data)} {game} cards (dry_run={dry_run})",
        extra={"correlation_id": session_id}
    )

    if not dry_run:
        db = get_db()
        collection = db["canonical_products"]

    stats = {"inserted": 0, "updated": 0, "errors": 0}

    for card_data in cards_data:
        try:
            # Validate using factory function
            product = create_tcg_product(
                game=game,
                set_code=card_data["set_code"],
                card_number=card_data["card_number"],
                name_jp=card_data.get("name_jp"),
                name_en=None,  # Yuyutei is JP-only
                rarity=card_data.get("rarity"),
                language="JP",
                image_url=card_data["image_url"],
                source_url=card_data["source_url"]
            )

            if dry_run:
                # Print to console for dry run
                print(f"✓ {product.id} - {card_data.get('name_jp', 'Unknown')}")
                price_str = f"¥{card_data.get('price_jpy')}" if card_data.get('price_jpy') else "N/A"
                print(f"  Rarity: {card_data.get('rarity')} | Price: {price_str}")
                stats["inserted"] += 1
            else:
                # Upsert to database
                product_dict = product.model_dump(by_alias=True)

                result = collection.update_one(
                    {"_id": product.id},
                    {"$set": product_dict},
                    upsert=True
                )

                if result.upserted_id:
                    stats["inserted"] += 1
                    logger.debug(f"Inserted: {product.id}")
                else:
                    stats["updated"] += 1
                    logger.debug(f"Updated: {product.id}")

                # Log price as metadata (not stored in product)
                if card_data.get("price_jpy"):
                    logger.info(
                        "Card price reference",
                        extra={
                            "game": game,
                            "card_id": product.id,
                            "price_jpy": card_data["price_jpy"],
                            "correlation_id": session_id
                        }
                    )

        except ValidationError as e:
            stats["errors"] += 1
            logger.error(
                "Validation failed",
                exc_info=True,
                extra={"game": game, "card_data": card_data, "correlation_id": session_id}
            )
        except Exception as e:
            stats["errors"] += 1
            logger.error(
                "Seeding failed",
                exc_info=True,
                extra={"game": game, "card_data": card_data, "correlation_id": session_id}
            )

    logger.info(
        f"Seeding complete for {game}",
        extra={
            "game": game,
            "stats": stats,
            "correlation_id": session_id
        }
    )

    return stats


@log_execution_time(logger)
def scrape_set_with_playwright(
    game: TCGGame,
    set_code: str,
    rarities: Optional[List[str]],
    max_pages: int,
    headless: bool,
    set_code_map: Dict[str, str],
    session_id: str
) -> List[Dict]:
    """
    Scrape a single set for a specific game using Playwright.

    Orchestrates the full scraping workflow:
    1. Launch browser
    2. Submit search form
    3. Scrape all pages
    4. Return card data

    Args:
        game: TCG game name
        set_code: Public set code (e.g., "OP01" or "SV2a")
        rarities: Optional list of rarities to filter
        max_pages: Maximum number of pages to scrape
        headless: Whether to run browser in headless mode
        set_code_map: Mapping from public to internal codes
        session_id: Correlation ID for logging

    Returns:
        List of card data dictionaries
    """
    logger.info(
        f"Scraping set: {set_code} ({game})",
        extra={
            "game": game,
            "set_code": set_code,
            "rarities": rarities,
            "max_pages": max_pages,
            "correlation_id": session_id
        }
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        # Create stealth context with anti-bot measures
        context = create_stealth_context(browser)
        page = context.new_page()

        try:
            # Navigate to search results using URL construction
            navigate_to_search_results(page, game, [set_code], set_code_map, rarities)

            # Scrape all pages
            cards = scrape_all_pages(page, game, max_pages)

            logger.info(
                f"Set {set_code} ({game}) complete",
                extra={
                    "game": game,
                    "set_code": set_code,
                    "cards_found": len(cards),
                    "correlation_id": session_id
                }
            )

            return cards

        except Exception as e:
            logger.error(
                f"Failed to scrape set {set_code} ({game})",
                exc_info=True,
                extra={
                    "game": game,
                    "set_code": set_code,
                    "correlation_id": session_id
                }
            )
            return []

        finally:
            browser.close()


def main():
    """
    Main CLI entry point.

    Parses arguments, discovers set codes, scrapes data, and seeds database.
    """
    parser = argparse.ArgumentParser(
        description="Yuyutei Multi-TCG Card Seeder - Scrapes canonical products",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # IMPORTANT: Always activate venv first
  source /Users/kenjifushida/Documents/dev/velodata/venv/bin/activate

  # One Piece - Dry run (validate without database writes, see browser)
  python services/seeders/yuyutei_seeder.py --game ONE_PIECE --sets OP01 OP02 --max-pages 3 --dry-run --headed

  # One Piece - Live run (seed database, headless)
  python services/seeders/yuyutei_seeder.py --game ONE_PIECE --sets OP14 --max-pages 10

  # One Piece - Filter by rarities (SR and P-SEC only)
  python services/seeders/yuyutei_seeder.py --game ONE_PIECE --sets OP01 OP14 --rarities SR P-SEC --max-pages 5

  # Pokemon - Scrape specific sets
  python services/seeders/yuyutei_seeder.py --game POKEMON --sets SV2a SV4a --max-pages 10

  # Yu-Gi-Oh! - All sets
  python services/seeders/yuyutei_seeder.py --game YUGIOH --all-sets --max-pages 20

  # Magic - Specific set with rarities
  python services/seeders/yuyutei_seeder.py --game MAGIC --sets BRO --rarities M R --max-pages 5
        """
    )

    parser.add_argument(
        "--game",
        required=True,
        choices=["POKEMON", "YUGIOH", "ONE_PIECE", "MAGIC"],
        help="TCG game to scrape"
    )
    parser.add_argument(
        "--sets",
        nargs="+",
        help="Set codes (game-specific, e.g., OP01 for One Piece, SV2a for Pokemon)"
    )
    parser.add_argument(
        "--all-sets",
        action="store_true",
        help="Scrape all available sets for the specified game"
    )
    parser.add_argument(
        "--rarities",
        nargs="+",
        help="Filter by rarities (game-specific, e.g., P-SEC/SR for One Piece, RR/RRR for Pokemon)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=10,
        help="Max pages per set (default: 10)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without database writes"
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode (for debugging)"
    )

    args = parser.parse_args()

    # Validation
    if not args.all_sets and not args.sets:
        parser.error("Either --sets or --all-sets required")

    headless = not args.headed
    session_id = str(uuid.uuid4())[:8]

    # Session start logging
    logger.info("=" * 60)
    logger.info(f"VELODATA - YUYUTEI {args.game} SEEDER")
    logger.info("=" * 60)
    logger.info(
        "Starting seeder session",
        extra={
            "session_id": session_id,
            "game": args.game,
            "sets": args.sets,
            "all_sets": args.all_sets,
            "rarities": args.rarities,
            "max_pages": args.max_pages,
            "dry_run": args.dry_run,
            "headless": headless
        }
    )

    try:
        # Single browser session for all operations
        logger.info("Launching browser session")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = create_stealth_context(browser)
            page = context.new_page()

            # Discover set code mapping
            logger.info(f"Phase 1: Discovering set code mapping for {args.game}")
            set_code_map = discover_and_map_sets(page, args.game)
            logger.info(f"Discovered {len(set_code_map)} set codes: {list(set_code_map.keys())}")

            # Determine which sets to scrape
            if args.all_sets:
                sets_to_scrape = list(set_code_map.keys())
                logger.info(f"Scraping ALL {args.game} sets: {sets_to_scrape}")
            else:
                sets_to_scrape = args.sets
                # Validate sets exist in mapping
                invalid_sets = [s for s in sets_to_scrape if s not in set_code_map]
                if invalid_sets:
                    logger.warning(f"Invalid set codes (not found in mapping): {invalid_sets}")
                    sets_to_scrape = [s for s in sets_to_scrape if s in set_code_map]
                    if not sets_to_scrape:
                        raise ValueError("No valid sets to scrape")
                logger.info(f"Scraping selected {args.game} sets: {sets_to_scrape}")

            # Scrape each set using the same browser/page
            logger.info("Phase 2: Scraping card data")
            all_cards = []
            for idx, set_code in enumerate(sets_to_scrape, 1):
                logger.info(f"Processing set {idx}/{len(sets_to_scrape)}: {set_code}")

                # Navigate to search results
                navigate_to_search_results(page, args.game, [set_code], set_code_map, args.rarities)

                # Scrape all pages
                cards = scrape_all_pages(page, args.game, args.max_pages)
                all_cards.extend(cards)

                logger.info(
                    f"Set {set_code} ({args.game}) complete",
                    extra={
                        "game": args.game,
                        "set_code": set_code,
                        "cards_found": len(cards),
                        "correlation_id": session_id
                    }
                )

                # Rate limit between sets
                if idx < len(sets_to_scrape):
                    delay = random.uniform(3, 5)
                    logger.debug(f"Rate limiting: waiting {delay:.1f}s before next set")
                    time.sleep(delay)

            browser.close()

        logger.info(f"Scraped {len(all_cards)} total {args.game} cards from {len(sets_to_scrape)} sets")

        # Seed database
        logger.info("Phase 3: Seeding canonical products")
        stats = seed_canonical_products(args.game, all_cards, args.dry_run, session_id)

        # Session summary
        logger.info("=" * 60)
        logger.info("SEEDER SESSION SUMMARY")
        logger.info("=" * 60)

        success_count = stats["inserted"] + stats["updated"]
        success_rate = (success_count / len(all_cards) * 100) if all_cards else 0

        logger.info(
            "Session completed",
            extra={
                "session_id": session_id,
                "game": args.game,
                "sets_scraped": len(sets_to_scrape),
                "cards_found": len(all_cards),
                "cards_inserted": stats["inserted"],
                "cards_updated": stats["updated"],
                "errors": stats["errors"],
                "success_rate": f"{success_rate:.1f}%"
            }
        )

        # Print summary to console
        print("\n" + "=" * 60)
        print(f"SEEDER SESSION SUMMARY - {args.game}")
        print("=" * 60)
        print(f"Session ID:       {session_id}")
        print(f"Game:             {args.game}")
        print(f"Sets Scraped:     {len(sets_to_scrape)}")
        print(f"Cards Found:      {len(all_cards)}")
        print(f"Cards Inserted:   {stats['inserted']}")
        print(f"Cards Updated:    {stats['updated']}")
        print(f"Errors:           {stats['errors']}")
        print(f"Success Rate:     {success_rate:.1f}%")
        print("=" * 60)

        if not args.dry_run:
            print(f"\n✓ Database seeding complete for {args.game}")
            print(f"  View logs: tail -f logs/yuyutei-seeder.log")
        else:
            print(f"\n✓ Dry run complete for {args.game} (no database writes)")

    except KeyboardInterrupt:
        logger.info("Seeder interrupted by user")
        print("\n\nSeeder interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.critical("Fatal error", exc_info=True, extra={"session_id": session_id})
        print(f"\n\n❌ Fatal error: {e}")
        print(f"   Check logs for details: logs/yuyutei-seeder.log")
        sys.exit(1)

    finally:
        if not args.dry_run:
            try:
                close_db()
                logger.debug("Database connection closed")
            except Exception as e:
                logger.error("Failed to close database connection", exc_info=True)


if __name__ == "__main__":
    main()
