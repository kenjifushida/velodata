#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PayPay Flea Market Scraper - Scrapes paypayfleamarket.yahoo.co.jp and saves to market_listings collection.

Scrapes product listings from PayPay Flea Market (Japanese secondhand marketplace) and stores them
in the market_listings MongoDB collection for later processing by the matching pipeline.

Supported Niches:
    - TCG: Trading Card Games (Pokemon, Yu-Gi-Oh!, One Piece, Magic)
    - WATCH: Luxury and vintage wristwatches
    - CAMERA_GEAR: Digital cameras, lenses, and photography equipment
    - LUXURY_ITEM: Designer bags, wallets, and accessories
    - VIDEOGAME: Game consoles
    - STATIONARY: Writing utensils, fountain pens, and office supplies
    - COLLECTION_FIGURES: Anime figures, collectible figurines, and model kits

Usage:
    # Dry run (don't save to database, just print)
    python paypay_scraper.py --niche TCG --keyword "ポケモンカード" --max-pages 2 --dry-run --headed

    # Live run (save to market_listings collection, headless)
    python paypay_scraper.py --niche TCG --keyword "ワンピースカード" --max-pages 5

    # Search for luxury watches
    python paypay_scraper.py --niche WATCH --keyword "ロレックス" --max-pages 3 --dry-run

    # Search for camera gear
    python paypay_scraper.py --niche CAMERA_GEAR --keyword "Canon EOS" --max-pages 5
"""
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import time
import uuid
import re
import random
import urllib.parse
from typing import List, Dict, Optional, Literal
from datetime import datetime
from pydantic import ValidationError

try:
    from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
except ImportError:
    print("playwright not installed. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
    from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from core.database import get_db, close_db
from core.models.market_listing import create_paypay_listing, MarketListing
from core.logging import get_logger, log_execution_time

# Initialize logger for this service
logger = get_logger("paypay-scraper")


# ============================================================================
# PAYPAY CONSTANTS
# ============================================================================

BASE_URL = "https://paypayfleamarket.yahoo.co.jp"

# Category IDs for PayPay Flea Market (used to filter searches by niche)
NICHE_CATEGORY_IDS: Dict[str, str] = {
    "TCG": "2511,2420",  # Trading Cards (includes Pokemon, Yu-Gi-Oh!, One Piece, etc.)
    "WATCH": "2425",  # Watches
    "CAMERA_GEAR": "2440,2442",  # Cameras and Camera Accessories
    "LUXURY_ITEM": "2435,2436",  # Bags and Wallets
    "VIDEOGAME": "2470,2472",  # Game Consoles
    "STATIONARY": "2480",  # Office Supplies
    "COLLECTION_FIGURES": "2485",  # Figures and Collectibles
}


# ============================================================================
# PLAYWRIGHT STEALTH CONFIGURATION
# ============================================================================

def create_stealth_context(browser: Browser) -> BrowserContext:
    """
    Create a stealth browser context with anti-bot measures.

    Args:
        browser: Playwright browser instance

    Returns:
        BrowserContext configured with stealth settings
    """
    # Randomize viewport to appear more human-like
    viewport_width = random.randint(1366, 1920)
    viewport_height = random.randint(768, 1080)

    logger.debug(
        f"Creating stealth context",
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


def simulate_human_behavior(page: Page, correlation_id: str):
    """
    Simulate human-like behavior on the page (mouse movements, scrolling).

    Args:
        page: Playwright page instance
        correlation_id: Session correlation ID for logging
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
        viewport_height = page.viewport_size['height']
        scroll_amount = 0
        max_scroll = random.randint(1000, 2000)

        while scroll_amount < max_scroll:
            scroll_step = random.randint(200, 500)
            page.evaluate(f"window.scrollBy(0, {scroll_step})")
            scroll_amount += scroll_step
            time.sleep(random.uniform(0.3, 0.8))

        # Occasionally scroll back up (20% chance)
        if random.random() < 0.2:
            page.evaluate("window.scrollBy(0, -300)")
            time.sleep(random.uniform(0.2, 0.5))

        # Scroll to top
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(random.uniform(0.5, 1.0))

        logger.debug(
            "Human behavior simulation complete",
            extra={"correlation_id": correlation_id}
        )

    except Exception as e:
        logger.warning(
            "Failed to simulate human behavior",
            exc_info=True,
            extra={"correlation_id": correlation_id}
        )


# ============================================================================
# TCG-SPECIFIC ATTRIBUTE EXTRACTION
# ============================================================================

def extract_tcg_attributes(title: str) -> Dict[str, Optional[str]]:
    """
    Extract TCG-specific attributes from product title.

    Args:
        title: Product title from PayPay listing

    Returns:
        Dictionary with extracted TCG attributes (game, set_code, card_number, rarity)
    """
    attributes = {
        "game": None,
        "set_code": None,
        "card_number": None,
        "rarity": None,
        "language": "JP",
    }

    # Detect game type from title keywords
    title_lower = title.lower()
    if any(keyword in title_lower for keyword in ["ポケモン", "ポケカ", "pokemon", "ピカチュウ", "リザードン"]):
        attributes["game"] = "POKEMON"
    elif any(keyword in title_lower for keyword in ["遊戯王", "yugioh", "yu-gi-oh", "ブルーアイズ"]):
        attributes["game"] = "YUGIOH"
    elif any(keyword in title_lower for keyword in ["ワンピース", "one piece", "ワンピ", "ルフィ", "ゾロ"]):
        attributes["game"] = "ONE_PIECE"
    elif any(keyword in title_lower for keyword in ["magic", "マジック", "mtg"]):
        attributes["game"] = "MAGIC"

    # Extract set code patterns
    # Pokemon: sv2a, sv1, sv4a, etc.
    # Yu-Gi-Oh!: BODE-EN, DIFO-JP, etc.
    # One Piece: OP01, OP02, etc.
    # Magic: BRO, DMU, etc.
    set_patterns = [
        r'sv\d+[a-z]?',  # Pokemon Scarlet/Violet: sv2a, sv1, sv4a
        r's\d+[a-z]?',   # Pokemon Sword/Shield: s8a, s6a
        r'OP\d+',        # One Piece: OP01, OP02
        r'[A-Z]{3,4}-[A-Z]{2}',  # Yu-Gi-Oh!: BODE-EN, DIFO-JP
        r'[A-Z]{3}',     # Magic: BRO, DMU
    ]

    for pattern in set_patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            attributes["set_code"] = match.group(0).upper()
            break

    # Extract card number patterns
    # Patterns: 165/165, #001, No.001, 001/100
    card_number_patterns = [
        r'(\d+)/\d+',    # 165/165 format
        r'#(\d+)',       # #001 format
        r'No\.?(\d+)',   # No.001 or No001 format
        r'(\d{3})',      # Raw 3-digit number (as fallback)
    ]

    for pattern in card_number_patterns:
        match = re.search(pattern, title)
        if match:
            attributes["card_number"] = match.group(1)
            break

    # Extract rarity
    rarity_keywords = {
        "UR": ["UR", "ウルトラレア", "ultra rare"],
        "SR": ["SR", "スーパーレア", "super rare"],
        "RR": ["RR", "ダブルレア", "double rare"],
        "R": ["R", "レア", " rare"],  # Space before "rare" to avoid matching "super rare"
        "SAR": ["SAR"],
        "AR": ["AR"],
        "Secret": ["シークレット", "secret"],
        "Promo": ["プロモ", "promo"],
    }

    for rarity_code, keywords in rarity_keywords.items():
        if any(keyword in title_lower for keyword in keywords):
            attributes["rarity"] = rarity_code
            break

    return attributes


# ============================================================================
# SCRAPING FUNCTIONS
# ============================================================================

@log_execution_time(logger)
def scrape_paypay_search(
    niche_type: Literal["TCG", "WATCH", "CAMERA_GEAR", "LUXURY_ITEM", "VIDEOGAME", "STATIONARY", "COLLECTION_FIGURES"],
    keyword: str,
    max_pages: int = 5,
    headless: bool = True,
    session_id: Optional[str] = None
) -> List[Dict]:
    """
    Scrape PayPay Flea Market search results for product listings.

    Args:
        niche_type: Product niche type
        keyword: Search keyword (Japanese or English)
        max_pages: Maximum number of pages to scrape
        headless: Whether to run browser in headless mode
        session_id: Scraping session correlation ID

    Returns:
        List of scraped product dictionaries
    """
    correlation_id = session_id or str(uuid.uuid4())[:8]
    logger.info(
        f"Starting PayPay scrape",
        extra={
            "niche_type": niche_type,
            "keyword": keyword,
            "max_pages": max_pages,
            "headless": headless,
            "correlation_id": correlation_id
        }
    )

    products = []

    with sync_playwright() as p:
        # Launch browser
        logger.info(
            f"Launching browser ({'headless' if headless else 'headed'} mode)",
            extra={"correlation_id": correlation_id}
        )
        browser = p.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )

        try:
            # Create stealth context
            context = create_stealth_context(browser)
            page = context.new_page()

            page_num = 1

            while page_num <= max_pages:
                try:
                    # Build search URL
                    encoded_keyword = urllib.parse.quote(keyword)
                    category_ids = NICHE_CATEGORY_IDS.get(niche_type, "")

                    # URL format: https://paypayfleamarket.yahoo.co.jp/search/{keyword}?sort=openTime&order=desc&categoryIds={ids}
                    url = f"{BASE_URL}/search/{encoded_keyword}?sort=openTime&order=desc"
                    if category_ids:
                        url += f"&categoryIds={category_ids}"
                    if page_num > 1:
                        url += f"&page={page_num}"

                    logger.debug(
                        f"Fetching page {page_num}",
                        extra={"url": url, "correlation_id": correlation_id}
                    )

                    # Navigate to page
                    response = page.goto(url, wait_until='networkidle', timeout=60000)

                    if not response or not response.ok:
                        status_code = response.status if response else "No response"
                        logger.error(
                            f"Failed to fetch page {page_num}",
                            extra={
                                "status_code": status_code,
                                "correlation_id": correlation_id
                            }
                        )
                        break

                    # Random delay to appear human-like
                    time.sleep(random.uniform(2, 4))

                    # Simulate human behavior
                    simulate_human_behavior(page, correlation_id)

                    # Find listing elements (try multiple selectors as fallbacks)
                    selectors_to_try = [
                        'a[href*="/item/"]',  # Proven selector from test
                        'article',
                        '[data-testid*="item"]',
                        '.item-card',
                    ]

                    listing_elements = None
                    successful_selector = None

                    for selector in selectors_to_try:
                        elements = page.locator(selector).all()
                        if elements and len(elements) > 0:
                            listing_elements = elements
                            successful_selector = selector
                            break

                    if not listing_elements:
                        logger.info(
                            f"No listings found on page {page_num}, stopping",
                            extra={"correlation_id": correlation_id}
                        )
                        break

                    logger.info(
                        f"Found {len(listing_elements)} listings on page {page_num}",
                        extra={
                            "count": len(listing_elements),
                            "selector": successful_selector,
                            "correlation_id": correlation_id
                        }
                    )

                    # Extract product data from each listing
                    for idx, element in enumerate(listing_elements):
                        try:
                            product_data = extract_product_from_element(
                                element,
                                niche_type,
                                correlation_id,
                                page
                            )
                            if product_data:
                                products.append(product_data)
                                logger.debug(
                                    f"Extracted product: {product_data.get('external_id')}",
                                    extra={"correlation_id": correlation_id}
                                )
                        except Exception as e:
                            logger.error(
                                f"Failed to extract product {idx + 1} on page {page_num}",
                                exc_info=True,
                                extra={"correlation_id": correlation_id}
                            )
                            continue

                    # Check if there's a next page
                    # Look for pagination button or next page link
                    next_page_exists = False
                    try:
                        # Try to find next page button
                        next_button = page.locator('a[aria-label*="次"], button:has-text("次へ"), a:has-text("次のページ")').first
                        if next_button.is_visible():
                            next_page_exists = True
                    except:
                        pass

                    if not next_page_exists and page_num < max_pages:
                        logger.info(
                            f"No more pages available after page {page_num}",
                            extra={"correlation_id": correlation_id}
                        )
                        break

                    # Rate limiting - be respectful
                    time.sleep(random.uniform(2, 4))
                    page_num += 1

                except Exception as e:
                    logger.error(
                        f"Error scraping page {page_num}",
                        exc_info=True,
                        extra={"correlation_id": correlation_id}
                    )
                    break

        finally:
            browser.close()

    logger.info(
        f"Scraping complete. Extracted {len(products)} products",
        extra={"total_products": len(products), "correlation_id": correlation_id}
    )

    return products


def extract_product_from_element(
    element,
    niche_type: str,
    correlation_id: str,
    page: Page
) -> Optional[Dict]:
    """
    Extract product data from a PayPay listing element.

    Args:
        element: Playwright locator element for listing
        niche_type: Product niche type
        correlation_id: Session correlation ID
        page: Playwright page instance

    Returns:
        Dictionary with product data or None if extraction fails
    """
    try:
        # Extract URL
        # If element is already an <a> tag, get href directly
        # Otherwise, find <a> child
        href = element.get_attribute('href')
        if not href:
            # Try to find link within element
            link = element.locator('a').first
            href = link.get_attribute('href') if link else None

        if not href:
            return None

        # Make absolute URL
        if href.startswith('http'):
            product_url = href
        else:
            product_url = BASE_URL + href

        # Extract external ID from URL (e.g., /item/abc123xyz -> abc123xyz)
        item_id_match = re.search(r'/item/([a-zA-Z0-9_-]+)', product_url)
        if not item_id_match:
            return None
        external_id = item_id_match.group(1)

        # Extract title
        # Try multiple methods to get title text
        title = None
        try:
            # Method 1: Try to find title element within listing
            title_elem = element.locator('[class*="title"], [class*="Title"], h2, h3').first
            if title_elem:
                title = title_elem.inner_text(timeout=1000).strip()
        except:
            pass

        if not title:
            try:
                # Method 2: Get all text content and use first meaningful line
                text = element.inner_text(timeout=1000).strip()
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                if lines:
                    # Assume first line that's not just a price is the title
                    for line in lines:
                        if not re.match(r'^[¥￥,\d]+円?$', line):
                            title = line
                            break
            except:
                pass

        if not title:
            title = f"PayPay Item {external_id}"

        # Extract price
        price_jpy = None
        try:
            # Find price text (format: ¥12,800 or 12,800円)
            price_elem = element.locator('[class*="price"], [class*="Price"]').first
            if price_elem:
                price_text = price_elem.inner_text(timeout=1000).strip()
                # Remove ¥, 円, commas
                price_text = re.sub(r'[¥￥,円]', '', price_text)
                price_jpy = int(price_text)
        except:
            pass

        if not price_jpy:
            # Try to find price in all text
            try:
                text = element.inner_text(timeout=1000)
                price_match = re.search(r'[¥￥]?([\d,]+)円?', text)
                if price_match:
                    price_text = price_match.group(1).replace(',', '')
                    price_jpy = int(price_text)
            except:
                pass

        if not price_jpy:
            logger.warning(
                f"Could not extract price for item {external_id}",
                extra={"external_id": external_id, "correlation_id": correlation_id}
            )
            return None

        # Extract image URLs
        image_urls = []
        try:
            # Find img elements within listing
            img_elements = element.locator('img').all()
            for img in img_elements[:3]:  # Limit to first 3 images
                src = img.get_attribute('src')
                if src and not src.startswith('data:') and 'blank' not in src.lower():
                    # Make absolute URL
                    if src.startswith('http'):
                        image_urls.append(src)
                    else:
                        image_urls.append(BASE_URL + src)
        except:
            pass

        # Extract niche-specific attributes
        attributes = {}

        if niche_type == "TCG":
            # Extract TCG-specific attributes from title
            tcg_attributes = extract_tcg_attributes(title)
            attributes.update(tcg_attributes)

        # Store raw title for future NLP processing
        attributes["raw_title"] = title

        return {
            "external_id": external_id,
            "niche_type": niche_type,
            "title": title,
            "price_jpy": price_jpy,
            "url": product_url,
            "image_urls": image_urls,
            "attributes": attributes,
            "scrape_session_id": correlation_id,
        }

    except Exception as e:
        logger.error(
            "Failed to extract product from element",
            exc_info=True,
            extra={"correlation_id": correlation_id}
        )
        return None


# ============================================================================
# DATABASE INSERTION
# ============================================================================

@log_execution_time(logger)
def insert_market_listings(products_data: List[Dict], dry_run: bool = False) -> int:
    """
    Insert scraped products into MongoDB market_listings collection.

    Only inserts if the listing doesn't already exist (checks by _id and URL).

    Args:
        products_data: List of scraped product dictionaries
        dry_run: If True, validate but don't insert to database

    Returns:
        Number of products successfully inserted
    """
    if dry_run:
        logger.info(f"DRY RUN MODE: Validating {len(products_data)} listings (no database writes)")
    else:
        logger.info(f"Inserting {len(products_data)} listings to market_listings collection")

    if not dry_run:
        db = get_db()
        collection = db["market_listings"]

    inserted_count = 0
    skipped_count = 0
    error_count = 0

    for product in products_data:
        try:
            # Create MarketListing using factory function
            listing = create_paypay_listing(
                external_id=product["external_id"],
                niche_type=product["niche_type"],
                title=product["title"],
                price_jpy=product["price_jpy"],
                url=product["url"],
                attributes=product["attributes"],
                image_urls=product.get("image_urls"),
                scrape_session_id=product.get("scrape_session_id"),
            )

            if dry_run:
                # In dry run, just print the listing
                print(f"\n{'='*70}")
                print(f"Listing ID: {listing.id}")
                print(f"Niche Type: {listing.niche_type}")
                print(f"Title: {listing.title}")
                print(f"Price: ¥{listing.price_jpy:,}")
                print(f"URL: {listing.url}")
                if listing.image_urls and len(listing.image_urls) > 0:
                    print(f"Images: {len(listing.image_urls)} image(s)")
                    for idx, img_url in enumerate(listing.image_urls[:3], 1):  # Show first 3
                        print(f"  [{idx}] {img_url}")
                print(f"Attributes: {listing.attributes}")
                print(f"Listed At: {listing.listed_at}")
                print(f"Is Processed: {listing.is_processed}")
                print(f"{'='*70}")
                inserted_count += 1
            else:
                # Check if listing already exists (by ID or URL)
                existing = collection.find_one({
                    "$or": [
                        {"_id": listing.id},
                        {"url": str(listing.url)}
                    ]
                })

                if existing:
                    # Determine if it's a duplicate by ID or URL
                    if existing.get("_id") == listing.id:
                        reason = "same ID"
                    else:
                        reason = "same URL"

                    logger.debug(
                        f"Listing already exists ({reason}), skipping: {listing.id}",
                        extra={"listing_id": listing.id, "reason": reason}
                    )
                    skipped_count += 1
                else:
                    # Convert to dict for MongoDB
                    listing_dict = listing.to_dict_for_db()

                    # Insert new listing
                    collection.insert_one(listing_dict)

                    logger.debug(
                        f"Inserted listing: {listing.id}",
                        extra={"listing_id": listing.id, "title": product['title']}
                    )
                    inserted_count += 1

        except ValidationError as e:
            error_count += 1
            logger.error(
                f"Validation failed for listing",
                exc_info=True,
                extra={"product": product.get('title', 'Unknown')}
            )
        except Exception as e:
            error_count += 1
            logger.error(
                f"Error inserting listing",
                exc_info=True,
                extra={"product": product.get('title', 'Unknown')}
            )

    if dry_run:
        logger.info(
            f"DRY RUN COMPLETE: {inserted_count} validated, {error_count} errors",
            extra={"validated": inserted_count, "errors": error_count, "total": len(products_data)}
        )
    else:
        logger.info(
            f"Insertion completed",
            extra={
                "inserted": inserted_count,
                "skipped": skipped_count,
                "errors": error_count,
                "total": len(products_data)
            }
        )

    return inserted_count


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="PayPay Flea Market Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to test scraping (headed mode, no database writes)
  python paypay_scraper.py --niche TCG --keyword "ポケモンカード" --max-pages 2 --dry-run --headed

  # Live run to scrape and save Pokemon cards (headless)
  python paypay_scraper.py --niche TCG --keyword "ポケモンカード sv2a" --max-pages 5

  # Search for One Piece cards
  python paypay_scraper.py --niche TCG --keyword "ワンピースカード" --max-pages 3

  # Search for luxury watches
  python paypay_scraper.py --niche WATCH --keyword "ロレックス" --max-pages 3 --dry-run

  # Search for camera gear
  python paypay_scraper.py --niche CAMERA_GEAR --keyword "Canon EOS" --max-pages 5
        """
    )
    parser.add_argument(
        "--niche",
        required=True,
        choices=["TCG", "WATCH", "CAMERA_GEAR", "LUXURY_ITEM", "VIDEOGAME", "STATIONARY", "COLLECTION_FIGURES"],
        help="Product niche type"
    )
    parser.add_argument(
        "--keyword",
        required=True,
        type=str,
        help="Search keyword in Japanese or English (e.g., 'ポケモンカード', 'ロレックス')"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Maximum number of pages to scrape (default: 5)"
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode (shows browser window)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate scraped data without saving to database"
    )

    args = parser.parse_args()

    # Log session start
    session_id = str(uuid.uuid4())[:8]
    logger.info("=" * 60)
    logger.info("VELODATA - PAYPAY FLEA MARKET SCRAPER")
    logger.info("=" * 60)
    logger.info(
        "Starting scraper session",
        extra={
            "session_id": session_id,
            "niche_type": args.niche,
            "keyword": args.keyword,
            "max_pages": args.max_pages,
            "headless": not args.headed,
            "dry_run": args.dry_run,
        }
    )

    total_scraped = 0
    total_seeded = 0

    try:
        # Scrape PayPay
        products_data = scrape_paypay_search(
            niche_type=args.niche,
            keyword=args.keyword,
            max_pages=args.max_pages,
            headless=not args.headed,
            session_id=session_id
        )

        total_scraped = len(products_data)

        if products_data:
            inserted = insert_market_listings(products_data, dry_run=args.dry_run)
            total_seeded = inserted
        else:
            logger.warning("No products found to insert", extra={"session_id": session_id})

    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user", extra={"session_id": session_id})
    except Exception as e:
        logger.critical("Fatal error occurred", exc_info=True, extra={"session_id": session_id})
    finally:
        if not args.dry_run:
            close_db()

    # Log final summary
    logger.info("=" * 60)
    logger.info("SCRAPER SESSION SUMMARY")
    logger.info("=" * 60)
    logger.info(
        "Session completed",
        extra={
            "session_id": session_id,
            "niche_type": args.niche,
            "keyword": args.keyword,
            "dry_run": args.dry_run,
            "products_scraped": total_scraped,
            "products_inserted": total_seeded,
            "success_rate": f"{(total_seeded/total_scraped*100):.1f}%" if total_scraped > 0 else "N/A"
        }
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
