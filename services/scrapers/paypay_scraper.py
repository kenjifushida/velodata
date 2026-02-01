#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PayPay Flea Market Scraper - Scrapes paypayfleamarket.yahoo.co.jp and saves to market_listings collection.

Scrapes product listings from PayPay Flea Market (Japanese secondhand marketplace) and stores them
in the market_listings MongoDB collection for later processing by the matching pipeline.

Supported Niches:
    - TCG: Trading Card Games (auto-detects game from title)
        - Pokemon Card Game (ポケモンカード)
        - Yu-Gi-Oh! (遊戯王)
        - One Piece Card Game (ワンピースカード)
        - Magic: The Gathering (MTG)
        - Weiss Schwarz (ヴァイスシュヴァルツ)
        - Dragon Ball Super Card Game
        - Digimon Card Game (デジモンカード)
        - Cardfight!! Vanguard (ヴァンガード)
        - Union Arena (ユニオンアリーナ)
        - Duel Masters (デュエルマスターズ)
    - WATCH: Luxury and vintage wristwatches
    - CAMERA_GEAR: Digital cameras, lenses, and photography equipment
    - LUXURY_ITEM: Designer bags, wallets, and accessories
    - VIDEOGAME: Game consoles
    - STATIONARY: Writing utensils, fountain pens, and office supplies
    - COLLECTION_FIGURES: Anime figures, collectible figurines, and model kits

Usage:
    # Dry run - Pokemon cards (Japanese)
    python paypay_scraper.py --niche TCG --keyword "ポケモンカード" --max-pages 2 --dry-run --headed

    # Dry run - One Piece cards
    python paypay_scraper.py --niche TCG --keyword "ワンピースカード" --max-pages 2 --dry-run

    # Dry run - Yu-Gi-Oh! cards
    python paypay_scraper.py --niche TCG --keyword "遊戯王" --max-pages 2 --dry-run

    # Dry run - Weiss Schwarz cards
    python paypay_scraper.py --niche TCG --keyword "ヴァイスシュヴァルツ" --max-pages 2 --dry-run

    # Dry run - Magic: The Gathering
    python paypay_scraper.py --niche TCG --keyword "MTG" --max-pages 2 --dry-run

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
from core.tcg_games import (
    TCGGame,
    TCGGameDetector,
    get_detector,
    detect_tcg_game,
    extract_tcg_card_info,
    ALL_GAME_CONFIGS,
)
from core.llm import translate

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
# TRANSLATION HELPER
# ============================================================================

def translate_title_safe(title: str, niche_type: str, enable_translation: bool = False) -> Optional[str]:
    """
    Safely translate a Japanese product title to English.

    Uses the LLM translation service with fallback to None on failure.
    Translation is non-blocking - scraping continues even if translation fails.

    Args:
        title: Japanese product title
        niche_type: Product niche for context (e.g., "TCG", "WATCH")
        enable_translation: Whether translation is enabled (default: False)

    Returns:
        English translation or None if translation fails/disabled
    """
    if not enable_translation:
        return None

    # Skip if title appears to already be in English
    # (contains mostly ASCII characters)
    ascii_ratio = sum(1 for c in title if ord(c) < 128) / len(title) if title else 0
    if ascii_ratio > 0.8:
        logger.debug(f"Title appears to be English, skipping translation")
        return title  # Return as-is

    try:
        # Map niche type to translation context for better accuracy
        context_map = {
            "TCG": "trading cards, collectibles",
            "WATCH": "luxury watches, timepieces",
            "CAMERA_GEAR": "camera equipment, photography",
            "LUXURY_ITEM": "designer goods, fashion accessories",
            "VIDEOGAME": "video games, gaming consoles",
            "STATIONARY": "writing instruments, office supplies",
            "COLLECTION_FIGURES": "anime figures, collectibles",
        }
        context = context_map.get(niche_type, "product listing")

        translated = translate(title, context=context)

        if translated and translated.strip():
            logger.debug(
                f"Translated title",
                extra={"original": title[:50], "translated": translated[:50]}
            )
            return translated.strip()
        return None

    except Exception as e:
        logger.warning(
            f"Translation failed, continuing without translation",
            extra={"title": title[:50], "error": str(e)}
        )
        return None


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
# ITEM PAGE IMAGE EXTRACTION
# ============================================================================

def fetch_item_images(
    page: Page,
    item_url: str,
    correlation_id: str
) -> List[str]:
    """
    Fetch high-quality images from a PayPay item detail page.

    Opens the item page and extracts all product images from the image slider.
    Uses the same selectors as paypay_scraper_urls.py for consistency.

    Args:
        page: Playwright page instance (will navigate to item_url)
        item_url: Full URL to the PayPay item page
        correlation_id: Session correlation ID for logging

    Returns:
        List of image URLs (high-quality, from auctions.c.yimg.jp domain)
    """
    image_urls = []

    try:
        # Navigate to item page
        response = page.goto(item_url, wait_until='networkidle', timeout=30000)

        if not response or not response.ok:
            logger.warning(
                "Failed to load item page for images",
                extra={
                    "url": item_url[:80],
                    "status": response.status if response else "No response",
                    "correlation_id": correlation_id
                }
            )
            return image_urls

        # Brief delay for dynamic content to load
        time.sleep(random.uniform(1.0, 1.5))

        # Primary selector: .slick-list contains all product images in the slider
        try:
            imgs = page.locator('.slick-list img').all()
            seen_urls = set()

            for img in imgs:
                src = img.get_attribute('src')
                if src and not src.startswith('data:') and src not in seen_urls:
                    # Filter to only product images (auctions.c.yimg.jp domain)
                    if 'auctions.c.yimg.jp' in src or 'yimg.jp/images' in src:
                        image_urls.append(src)
                        seen_urls.add(src)

            if image_urls:
                logger.debug(
                    f"Extracted {len(image_urls)} images from item page",
                    extra={"url": item_url[:50], "correlation_id": correlation_id}
                )
        except Exception as e:
            logger.warning(
                "Failed to extract images from .slick-list",
                extra={"error": str(e), "correlation_id": correlation_id}
            )

        # Fallback: Try other slider/gallery selectors
        if not image_urls:
            try:
                imgs = page.locator('[class*="slider"] img, [class*="gallery"] img').all()
                seen_urls = set()

                for img in imgs:
                    src = img.get_attribute('src')
                    if src and 'auctions.c.yimg.jp' in src and src not in seen_urls:
                        image_urls.append(src)
                        seen_urls.add(src)
            except Exception:
                pass

    except Exception as e:
        logger.error(
            "Error fetching item page images",
            exc_info=True,
            extra={"url": item_url[:80], "correlation_id": correlation_id}
        )

    return image_urls


# ============================================================================
# TCG-SPECIFIC ATTRIBUTE EXTRACTION
# ============================================================================

def extract_tcg_attributes(title: str) -> Dict[str, Optional[str]]:
    """
    Extract TCG-specific attributes from product title.

    Uses the centralized TCGGameDetector for robust game detection and
    card info extraction across multiple TCG games.

    Supported Games:
        - Pokemon Card Game (ポケモンカード)
        - Yu-Gi-Oh! (遊戯王)
        - One Piece Card Game (ワンピースカード)
        - Magic: The Gathering (MTG)
        - Weiss Schwarz (ヴァイスシュヴァルツ)
        - Dragon Ball Super Card Game
        - Digimon Card Game (デジモンカード)
        - Cardfight!! Vanguard (ヴァンガード)
        - Union Arena (ユニオンアリーナ)
        - Duel Masters (デュエルマスターズ)

    Args:
        title: Product title from PayPay listing (Japanese or English)

    Returns:
        Dictionary with extracted TCG attributes:
        - game: TCG game type (POKEMON, YUGIOH, ONE_PIECE, etc.)
        - set_code: Set/expansion code
        - card_number: Card number within set
        - rarity: Card rarity
        - language: Card language (JP, EN, etc.)
        - raw_title: Original title for debugging
    """
    # Use centralized TCG game detector
    card_info = extract_tcg_card_info(title)

    # Add raw_title for debugging and future NLP processing
    card_info["raw_title"] = title

    logger.debug(
        f"Extracted TCG attributes",
        extra={
            "title": title[:50] if title else None,
            "game": card_info.get("game"),
            "set_code": card_info.get("set_code"),
            "rarity": card_info.get("rarity"),
        }
    )

    return card_info


def get_tcg_game_display_name(game: Optional[str]) -> str:
    """
    Get display name for a TCG game.

    Args:
        game: TCG game string (e.g., "POKEMON", "YUGIOH")

    Returns:
        Display name (e.g., "Pokemon Card Game", "Yu-Gi-Oh!")
    """
    if not game:
        return "Unknown TCG"

    try:
        tcg_game = TCGGame(game)
        config = ALL_GAME_CONFIGS.get(tcg_game)
        return config.display_name_en if config else game
    except ValueError:
        return game


# ============================================================================
# SCRAPING FUNCTIONS
# ============================================================================

@log_execution_time(logger)
def scrape_paypay_search(
    niche_type: Literal["TCG", "WATCH", "CAMERA_GEAR", "LUXURY_ITEM", "VIDEOGAME", "STATIONARY", "COLLECTION_FIGURES"],
    keyword: str,
    max_pages: int = 5,
    headless: bool = True,
    session_id: Optional[str] = None,
    enable_translation: bool = False,
    fetch_images: bool = False
) -> List[Dict]:
    """
    Scrape PayPay Flea Market search results for product listings.

    Args:
        niche_type: Product niche type
        keyword: Search keyword (Japanese or English)
        max_pages: Maximum number of pages to scrape
        headless: Whether to run browser in headless mode
        session_id: Scraping session correlation ID
        enable_translation: Whether to translate titles to English (default: False)
        fetch_images: Whether to fetch high-quality images from item pages (default: False)

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
            "fetch_images": fetch_images,
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
                    page_products = []
                    for idx, element in enumerate(listing_elements):
                        try:
                            product_data = extract_product_from_element(
                                element,
                                niche_type,
                                correlation_id,
                                page,
                                enable_translation=enable_translation
                            )
                            if product_data:
                                page_products.append(product_data)
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

                    # Fetch high-quality images from item pages if enabled
                    if fetch_images and page_products:
                        logger.info(
                            f"Fetching images for {len(page_products)} products",
                            extra={"page": page_num, "correlation_id": correlation_id}
                        )
                        for idx, product in enumerate(page_products):
                            item_url = product.get("url")
                            if item_url:
                                try:
                                    item_images = fetch_item_images(page, item_url, correlation_id)
                                    if item_images:
                                        product["image_urls"] = item_images
                                        logger.debug(
                                            f"Fetched {len(item_images)} images for {product.get('external_id')}",
                                            extra={"correlation_id": correlation_id}
                                        )
                                    # Rate limiting between item page fetches
                                    if idx < len(page_products) - 1:
                                        time.sleep(random.uniform(1.5, 2.5))
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to fetch images for {product.get('external_id')}",
                                        extra={"error": str(e), "correlation_id": correlation_id}
                                    )

                    products.extend(page_products)

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
    page: Page,
    enable_translation: bool = False
) -> Optional[Dict]:
    """
    Extract product data from a PayPay listing element.

    Args:
        element: Playwright locator element for listing
        niche_type: Product niche type
        correlation_id: Session correlation ID
        page: Playwright page instance
        enable_translation: Whether to translate titles to English

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
        # PayPay stores the product title in the img alt attribute
        title = None
        try:
            # Method 1: Get title from image alt attribute (most reliable)
            img_elem = element.locator('img').first
            if img_elem:
                alt_text = img_elem.get_attribute('alt')
                if alt_text and alt_text.strip():
                    title = alt_text.strip()
        except:
            pass

        if not title:
            try:
                # Method 2: Try to find title element within listing
                title_elem = element.locator('[class*="title"], [class*="Title"], h2, h3').first
                if title_elem:
                    title = title_elem.inner_text(timeout=1000).strip()
            except:
                pass

        if not title:
            try:
                # Method 3: Get all text content and use first meaningful line
                text = element.inner_text(timeout=1000).strip()
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                if lines:
                    # Assume first line that's not just a price or button text is the title
                    skip_phrases = ['いいね', '対象', '円']
                    for line in lines:
                        if not re.match(r'^[¥￥,\d]+円?$', line) and not any(skip in line for skip in skip_phrases):
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

        # Translate title (Japanese -> English)
        if enable_translation:
            title_en = translate_title_safe(title, niche_type, enable_translation)
            if title_en:
                attributes["title_en"] = title_en

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
                # In dry run, print the listing with formatted output
                attrs = listing.attributes
                print(f"\n{'='*70}")
                print(f"Listing ID: {listing.id}")
                print(f"Niche Type: {listing.niche_type}")

                # Show TCG-specific info if applicable
                if listing.niche_type == "TCG" and attrs.get("game"):
                    game_display = get_tcg_game_display_name(attrs.get("game"))
                    print(f"TCG Game:   {game_display} ({attrs.get('game')})")
                    if attrs.get("set_code"):
                        print(f"Set Code:   {attrs.get('set_code')}")
                    if attrs.get("card_number"):
                        print(f"Card #:     {attrs.get('card_number')}")
                    if attrs.get("rarity"):
                        print(f"Rarity:     {attrs.get('rarity')}")
                    if attrs.get("language"):
                        print(f"Language:   {attrs.get('language')}")

                print(f"Title (JP): {listing.title}")
                if attrs.get("title_en"):
                    print(f"Title (EN): {attrs['title_en']}")
                print(f"Price:      ¥{listing.price_jpy:,}")
                print(f"URL:        {listing.url}")
                if listing.image_urls and len(listing.image_urls) > 0:
                    print(f"Images:     {len(listing.image_urls)} image(s)")
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

  # Scrape with high-quality images (opens each item page)
  python paypay_scraper.py --niche TCG --keyword "ポケモンカード" --max-pages 2 --fetch-images --dry-run

  # Search for One Piece cards
  python paypay_scraper.py --niche TCG --keyword "ワンピースカード" --max-pages 3

  # Search for luxury watches
  python paypay_scraper.py --niche WATCH --keyword "ロレックス" --max-pages 3 --dry-run

  # Search for camera gear with high-quality images
  python paypay_scraper.py --niche CAMERA_GEAR --keyword "Canon EOS" --max-pages 5 --fetch-images
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
    parser.add_argument(
        "--translate",
        action="store_true",
        help="Enable Japanese to English title translation using LLM (default: disabled)"
    )
    parser.add_argument(
        "--fetch-images",
        action="store_true",
        help="Fetch high-quality images by opening each item page (slower but better images)"
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
            "translate": args.translate,
            "fetch_images": args.fetch_images,
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
            session_id=session_id,
            enable_translation=args.translate,
            fetch_images=args.fetch_images
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
