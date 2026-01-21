#!/usr/bin/env python3
"""
SNKRDUNK Sold Items Scraper - Daily price aggregations from SNKRDUNK.

Scrapes sold item prices for TCG cards from SNKRDUNK (snkrdunk.com) and stores
daily aggregations for arbitrage comparison with PayPay/Mercari listings.

Architecture:
- Uses Playwright with stealth mode (anti-bot measures)
- Scrapes sold items by condition rank (PSA10, A, B for TCG)
- Aggregates prices daily per canonical product
- Stores in sold_items_daily_agg collection

URL Structure:
- Pokemon cards: /apparel-categories/25?department_name=hobby&brand_id=pokemon
- Yu-Gi-Oh cards: /apparel-categories/25?department_name=hobby&brand_id=yu-gi-oh
- One Piece cards: /apparel-categories/25?department_name=hobby&brand_id=onepiece
- Individual items: /apparel-free-used-items/{id}

Usage:
    # Activate venv first
    source venv/bin/activate

    # Dry run - validate without database writes
    python services/scrapers/snkrdunk_sold_scraper.py --game POKEMON --dry-run --headed

    # Production run - headless, save to database
    python services/scrapers/snkrdunk_sold_scraper.py --game POKEMON --max-pages 5

    # All games
    python services/scrapers/snkrdunk_sold_scraper.py --game ALL --max-pages 10
"""
import argparse
import sys
import time
import random
import uuid
import re
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Optional, Literal
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

from core.models.sold_item import (
    MarketplaceSource,
    SoldItemDailyAgg,
    create_snkrdunk_daily_agg,
    should_store_tcg_rank,
    TCG_RANKS_TO_STORE,
)
from core.database import get_db, close_db
from core.logging import get_logger, log_execution_time

# Initialize logger
logger = get_logger("snkrdunk-scraper")

# Type aliases
TCGGame = Literal["POKEMON", "YUGIOH", "ONE_PIECE", "ALL"]

# ============================================================================
# CONFIGURATION
# ============================================================================

SNKRDUNK_BASE_URL = "https://snkrdunk.com"

# Game to brand_id mapping for SNKRDUNK URL
# Title examples from SNKRDUNK:
#   "スピアー R: マスターボールミラー[SV2a 015/165](強化拡張パック「ポケモンカード151」)"
#   "シャワーズV SR: SA[S6a 075/069](強化拡張パック「イーブイヒーローズ」)"
#   "ピカチュウex SAR [SV8a 205/187](ハイクラスパック「テラスタルフェスex」)"
GAME_CONFIG = {
    "POKEMON": {
        "brand_id": "pokemon",
        "display_name": "Pokemon",
        # Match formats: [SV2a 015/165], [S6a 075/069], [s8a 001/028], [M2a 247/193]
        "set_pattern": r'\[([A-Za-z]{1,3}\d{1,2}[a-z]?)\s+\d{3}/\d{3}\]',  # [SV2a 015/165]
        "card_pattern": r'\[([A-Za-z]{1,3}\d{1,2}[a-z]?)\s+(\d{3})/\d{3}\]',  # [SV2a 015/165] -> (SV2a, 015)
    },
    "YUGIOH": {
        "brand_id": "yu-gi-oh",
        "display_name": "Yu-Gi-Oh!",
        "set_pattern": r'([A-Z]{2,4}-[A-Z]{2})',
        "card_pattern": r'([A-Z]{2,4}-[A-Z]{2})(\d{3})',
    },
    "ONE_PIECE": {
        "brand_id": "onepiece",
        "display_name": "One Piece",
        # Match formats: [OP01-001], [ST01-001]
        "set_pattern": r'\[?([A-Z]{2,3}\d{2})[_\-\s]?',  # OP01, ST01
        "card_pattern": r'\[?([A-Z]{2,3}\d{2})[_\-\s]?(\d{3})',  # OP01-001
    },
}

# SNKRDUNK rank normalization
# Based on actual page data: PSA10, PSA9, PSA8以下, ARS10, A, B, C, D
SNKRDUNK_RANK_MAP = {
    # PSA grades (exact matches from page)
    "PSA10": "PSA10",
    "PSA 10": "PSA10",
    "PSA9": "A",
    "PSA 9": "A",
    "PSA8": "B",
    "PSA 8": "B",
    "PSA8以下": "B",  # PSA8 or below
    "PSA7": "B",
    "PSA 7": "B",
    # ARS grades (alternative grading company)
    "ARS10": "PSA10",  # Treat ARS10 as equivalent to PSA10
    "ARS 10": "PSA10",
    "ARS9": "A",
    # BGS grades
    "BGS10": "PSA10",
    "BGS 10": "PSA10",
    "BGS9.5": "A",
    "BGS 9.5": "A",
    # Simple letter grades (most common on SNKRDUNK)
    "A": "A",
    "B": "B",
    "C": "C",
    "D": "D",
    # Japanese condition ranks
    "ランクA": "A",
    "Aランク": "A",
    "美品": "A",
    "ランクB": "B",
    "Bランク": "B",
    "良品": "B",
    "ランクC": "C",
    "Cランク": "C",
    "並品": "C",
    "ランクD": "D",
    "Dランク": "D",
    "傷あり": "D",
}


# ============================================================================
# PLAYWRIGHT STEALTH CONFIGURATION
# ============================================================================

def create_stealth_context(browser: Browser) -> BrowserContext:
    """Create a stealth browser context with anti-bot measures."""
    viewport_width = random.randint(1366, 1920)
    viewport_height = random.randint(768, 1080)

    logger.debug(
        "Creating stealth context",
        extra={"viewport_width": viewport_width, "viewport_height": viewport_height}
    )

    context = browser.new_context(
        viewport={'width': viewport_width, 'height': viewport_height},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        locale='ja-JP',
        timezone_id='Asia/Tokyo',
    )

    # Override navigator.webdriver
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)

    return context


def simulate_human_behavior(page: Page):
    """Simulate human-like behavior on the page."""
    try:
        # Random mouse movements
        for _ in range(random.randint(2, 3)):
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            page.mouse.move(x, y)
            time.sleep(random.uniform(0.1, 0.2))

        # Scroll down incrementally
        scroll_amount = 0
        max_scroll = random.randint(800, 1500)
        while scroll_amount < max_scroll:
            scroll_step = random.randint(200, 400)
            page.evaluate(f"window.scrollBy(0, {scroll_step})")
            scroll_amount += scroll_step
            time.sleep(random.uniform(0.3, 0.6))

    except Exception as e:
        logger.warning(f"Human behavior simulation failed: {e}")


def save_debug_artifacts(page: Page, name: str, session_id: str):
    """Save screenshot and HTML for debugging."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_dir = project_root / "debug"
    debug_dir.mkdir(exist_ok=True)

    try:
        screenshot_path = debug_dir / f"snkrdunk_{name}_{session_id}_{timestamp}.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        logger.debug(f"Screenshot saved: {screenshot_path}")

        html_path = debug_dir / f"snkrdunk_{name}_{session_id}_{timestamp}.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(page.content())
        logger.debug(f"HTML saved: {html_path}")
    except Exception as e:
        logger.warning(f"Failed to save debug artifacts: {e}")


# ============================================================================
# SCRAPING FUNCTIONS
# ============================================================================

def build_category_url(game: str, page_num: int = 1) -> str:
    """
    Build SNKRDUNK category URL for trading cards (used/secondhand).

    Note: SNKRDUNK shows used items when clicking the "中古" (used) tab on the page.
    The URL structure uses /apparel-categories/25 for trading cards.

    Args:
        game: Game type (POKEMON, YUGIOH, ONE_PIECE)
        page_num: Page number for pagination

    Returns:
        Full URL string
    """
    config = GAME_CONFIG[game]
    base_url = f"{SNKRDUNK_BASE_URL}/apparel-categories/25"

    params = [
        f"department_name=hobby",
        f"brand_id={config['brand_id']}",
    ]

    if page_num > 1:
        params.append(f"page={page_num}")

    return f"{base_url}?{'&'.join(params)}"


def normalize_rank(raw_rank: str) -> Optional[str]:
    """
    Normalize SNKRDUNK rank to standard format.

    Args:
        raw_rank: Raw rank string from page

    Returns:
        Normalized rank (PSA10, A, B, C, D) or None
    """
    if not raw_rank:
        return None

    raw_rank = raw_rank.strip()

    # Direct mapping
    if raw_rank in SNKRDUNK_RANK_MAP:
        return SNKRDUNK_RANK_MAP[raw_rank]

    # Check for partial matches
    for key, value in SNKRDUNK_RANK_MAP.items():
        if key in raw_rank:
            return value

    # Default based on keywords
    raw_lower = raw_rank.lower()
    if 'psa' in raw_lower and '10' in raw_lower:
        return "PSA10"
    elif 'psa' in raw_lower and '9' in raw_lower:
        return "A"
    elif '美品' in raw_rank or 'a' in raw_lower:
        return "A"
    elif '良品' in raw_rank or 'b' in raw_lower:
        return "B"

    logger.warning(f"Unknown rank: {raw_rank}")
    return None


def extract_card_info(title: str, game: str) -> Optional[Dict]:
    """
    Extract card info from item title.

    Args:
        title: Item title string
        game: Game type

    Returns:
        Dict with set_code, card_number, or None
    """
    config = GAME_CONFIG[game]

    # Try card pattern first (set + number)
    card_match = re.search(config['card_pattern'], title, re.IGNORECASE)
    if card_match:
        return {
            "set_code": card_match.group(1).upper(),
            "card_number": card_match.group(2),
        }

    # Try set pattern only
    set_match = re.search(config['set_pattern'], title, re.IGNORECASE)
    if set_match:
        return {
            "set_code": set_match.group(1).upper(),
            "card_number": None,
        }

    return None


def extract_price(text: str) -> Optional[int]:
    """Extract price in JPY from text."""
    # Match patterns like "15,000円" or "15000円" or "¥15,000"
    price_match = re.search(r'[¥￥]?\s*(\d{1,3}(?:,\d{3})*)\s*円?', text)
    if price_match:
        price_str = price_match.group(1).replace(',', '')
        try:
            return int(price_str)
        except ValueError:
            pass
    return None


@log_execution_time(logger)
def scrape_sold_items_page(
    page: Page,
    game: str,
    session_id: str
) -> List[Dict]:
    """
    Scrape sold items from current page.

    DOM Structure (based on analysis):
    - ul.item-list-box > li.item-list (item containers)
    - a.item-block (clickable card with href like /apparels/{id}/used/{listing_id})
    - div.img-box > img (card image with alt=title)
    - p.item-price (price like "¥6,500 /PSA10")

    Args:
        page: Playwright page object
        game: Game type
        session_id: Session correlation ID

    Returns:
        List of sold item dictionaries
    """
    sold_items = []

    # Primary selector: item list items with used items
    # The page uses li.item-list.used for used/secondhand items
    item_selectors = [
        'li.item-list.used',  # Primary: used item cards
        'li.item-list',       # Fallback: all item cards
        'ul.item-list-box > li',  # Parent container approach
        'a.item-block',       # Direct link approach
    ]

    items = None
    used_selector = None

    for selector in item_selectors:
        elements = page.locator(selector)
        count = elements.count()
        if count > 0:
            items = elements
            used_selector = selector
            logger.debug(f"Found {count} items with selector: {selector}")
            break

    if not items or items.count() == 0:
        logger.warning("No sold items found on page")
        save_debug_artifacts(page, "no_items", session_id)
        return []

    item_count = items.count()
    logger.info(f"Processing {item_count} sold items with selector: {used_selector}")

    for i in range(item_count):
        try:
            item = items.nth(i)

            # Extract item link for href
            link = item.locator('a.item-block').first if 'li' in used_selector else item
            href = link.get_attribute('href') if link else None

            # Extract title from image alt or inner text
            img = item.locator('img').first
            title = img.get_attribute('alt') if img and img.count() > 0 else None
            if not title:
                title = item.inner_text().split('\n')[0]

            # Extract price text (format: "¥6,500 /PSA10")
            price_elem = item.locator('p.item-price').first
            if price_elem and price_elem.count() > 0:
                price_text = price_elem.inner_text()
            else:
                price_text = item.inner_text()

            # Extract price
            price = extract_price(price_text)
            if not price:
                logger.debug(f"No price found in: {price_text[:50]}")
                continue

            # Extract rank from price text (format: "¥6,500 /PSA10" or "¥2,500 /A")
            rank = None
            # Try extracting rank after the slash
            rank_match = re.search(r'/\s*(\w+)', price_text)
            if rank_match:
                raw_rank = rank_match.group(1).strip()
                rank = normalize_rank(raw_rank)

            # Fallback: check for rank keywords in full text
            if not rank:
                for rank_keyword in SNKRDUNK_RANK_MAP.keys():
                    if rank_keyword in price_text:
                        rank = normalize_rank(rank_keyword)
                        break

            if not rank:
                rank = "A"  # Default to A if no rank specified
                logger.debug(f"Using default rank A for: {title[:30] if title else 'unknown'}")

            # Filter TCG ranks (only keep PSA10, A, B)
            if not should_store_tcg_rank("TCG", rank):
                logger.debug(f"Skipping rank {rank} (not in PSA10, A, B)")
                continue

            # Extract card info from title
            card_info = extract_card_info(title, game) if title else None
            if not card_info or not card_info.get('set_code'):
                logger.debug(f"Could not extract card info from: {title[:50] if title else 'no title'}")
                continue

            # Build canonical product ID
            if card_info.get('card_number'):
                canonical_id = f"{game.lower().replace('_', '-')}-{card_info['set_code']}-{card_info['card_number']}"
            else:
                canonical_id = f"{game.lower().replace('_', '-')}-{card_info['set_code']}"

            sold_item = {
                "canonical_product_id": canonical_id,
                "title": title[:100] if title else "",
                "price_jpy": price,
                "rank": rank,
                "set_code": card_info['set_code'],
                "card_number": card_info.get('card_number'),
                "href": href,
            }

            sold_items.append(sold_item)
            logger.debug(f"Extracted: {canonical_id} - ¥{price:,} ({rank})")

        except Exception as e:
            logger.warning(f"Failed to extract item {i}: {e}")
            continue

    logger.info(f"Extracted {len(sold_items)} valid sold items from page")
    return sold_items


def click_used_tab(page: Page) -> bool:
    """
    Click on the "中古" (used) tab to view secondhand items.

    Returns:
        True if tab was clicked or already active, False on error
    """
    try:
        used_tab = page.locator('li.status-switch-tab-item:has-text("中古")')
        if used_tab.count() > 0:
            tab_class = used_tab.first.get_attribute('class') or ''
            if 'active' not in tab_class:
                logger.debug("Clicking on 中古 (used) tab")
                used_tab.first.click()
                time.sleep(random.uniform(2, 3))  # Wait for tab switch
                return True
            else:
                logger.debug("中古 (used) tab already active")
                return True
    except Exception as e:
        logger.warning(f"Could not interact with used tab: {e}")
    return False


def click_pagination_js(page: Page, page_num: int) -> bool:
    """
    Click on a pagination link using JavaScript (Vue-based pagination).

    Args:
        page: Playwright page object
        page_num: Page number to navigate to

    Returns:
        True if navigation was successful, False otherwise
    """
    try:
        # Scroll to bottom to ensure pagination is rendered
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(1)

        # Click pagination link via JavaScript
        result = page.evaluate(f'''
            () => {{
                const pagerLinks = document.querySelectorAll("ul.pager li.num a");
                for (let link of pagerLinks) {{
                    if (link.textContent.trim() === "{page_num}") {{
                        link.click();
                        return true;
                    }}
                }}
                return false;
            }}
        ''')

        if result:
            logger.debug(f"Clicked pagination link for page {page_num}")
            time.sleep(random.uniform(3, 4))  # Wait for content to load
            return True
        else:
            logger.debug(f"Pagination link for page {page_num} not found")
            return False

    except Exception as e:
        logger.warning(f"Failed to click pagination via JS: {e}")
        return False


@log_execution_time(logger)
def scrape_game_sold_items(
    page: Page,
    game: str,
    max_pages: int,
    session_id: str
) -> List[Dict]:
    """
    Scrape all sold items for a game across multiple pages.

    Pagination on SNKRDUNK is Vue-controlled and requires JavaScript clicks
    rather than URL navigation.

    Args:
        page: Playwright page object
        game: Game type
        max_pages: Maximum pages to scrape
        session_id: Session correlation ID

    Returns:
        List of all sold item dictionaries
    """
    all_items = []
    config = GAME_CONFIG[game]

    logger.info(f"Starting sold items scrape for {config['display_name']}")

    # Navigate to the category page
    url = build_category_url(game, page_num=1)
    logger.info(f"Loading category page: {url}")

    try:
        page.goto(url, wait_until="load", timeout=60000)
        time.sleep(random.uniform(3, 5))  # Wait for JS rendering

        # Click on "中古" (used) tab first
        if not click_used_tab(page):
            logger.warning("Could not switch to used items tab")

        simulate_human_behavior(page)

        # Check if page loaded properly
        title = page.title()
        if not title or "404" in title.lower():
            logger.warning(f"Page not found or invalid: {url}")
            return []

    except Exception as e:
        logger.error(f"Failed to load initial page: {e}", exc_info=True)
        save_debug_artifacts(page, "error_initial", session_id)
        return []

    # Scrape pages
    for page_num in range(1, max_pages + 1):
        logger.info(f"Scraping page {page_num}/{max_pages}")

        try:
            # For pages after the first, use JavaScript pagination
            if page_num > 1:
                if not click_pagination_js(page, page_num):
                    logger.info(f"No more pages available (stopped at page {page_num - 1})")
                    break

                # Ensure we're still on used items tab after pagination
                click_used_tab(page)

            # Extract sold items from current page
            items = scrape_sold_items_page(page, game, session_id)
            all_items.extend(items)

            if len(items) == 0:
                logger.info("No items found on current page, stopping pagination")
                break

            # Rate limiting between pages
            if page_num < max_pages:
                delay = random.uniform(2, 4)
                logger.debug(f"Rate limiting: waiting {delay:.1f}s")
                time.sleep(delay)

        except Exception as e:
            logger.error(f"Failed to scrape page {page_num}: {e}", exc_info=True)
            save_debug_artifacts(page, f"error_page{page_num}", session_id)
            break

    logger.info(f"Scraped {len(all_items)} total sold items for {config['display_name']}")
    return all_items


# ============================================================================
# AGGREGATION FUNCTIONS
# ============================================================================

def aggregate_sold_items(
    sold_items: List[Dict],
    game: str,
    scrape_date: date,
    session_id: str
) -> List[SoldItemDailyAgg]:
    """
    Aggregate sold items into daily statistics.

    Groups by: canonical_product_id + normalized_rank

    Args:
        sold_items: List of raw sold item dictionaries
        game: Game type
        scrape_date: Date of scraping
        session_id: Session correlation ID

    Returns:
        List of SoldItemDailyAgg objects
    """
    logger.info(f"Aggregating {len(sold_items)} sold items")

    # Group by product + rank
    groups = defaultdict(list)
    for item in sold_items:
        key = (item['canonical_product_id'], item['rank'])
        groups[key].append(item['price_jpy'])

    aggregations = []
    for (canonical_id, rank), prices in groups.items():
        if not prices:
            continue

        try:
            agg = create_snkrdunk_daily_agg(
                canonical_product_id=canonical_id,
                niche_type="TCG",
                rank=rank,
                sale_date=scrape_date,
                min_price_jpy=min(prices),
                max_price_jpy=max(prices),
                avg_price_jpy=sum(prices) / len(prices),
                sale_count=len(prices),
                median_price_jpy=sorted(prices)[len(prices) // 2] if prices else None,
                scrape_session_id=session_id,
            )
            aggregations.append(agg)

        except Exception as e:
            logger.error(f"Failed to create aggregation for {canonical_id}/{rank}: {e}")
            continue

    logger.info(f"Created {len(aggregations)} daily aggregations")
    return aggregations


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

@log_execution_time(logger)
def save_aggregations(
    aggregations: List[SoldItemDailyAgg],
    dry_run: bool,
    session_id: str
) -> Dict[str, int]:
    """
    Save aggregations to database.

    Args:
        aggregations: List of aggregation objects
        dry_run: If True, only validate without saving
        session_id: Session correlation ID

    Returns:
        Stats dictionary with inserted/updated/errors counts
    """
    stats = {"inserted": 0, "updated": 0, "errors": 0}

    if dry_run:
        logger.info("DRY RUN - Validating aggregations without saving")
        for agg in aggregations:
            print(f"✓ {agg.id}")
            print(f"    {agg.canonical_product_id} | {agg.normalized_rank}")
            print(f"    Avg: ¥{agg.avg_price_jpy:,.0f} | Count: {agg.sale_count}")
            print(f"    Range: ¥{agg.min_price_jpy:,} - ¥{agg.max_price_jpy:,}")
            stats["inserted"] += 1
        return stats

    db = get_db()
    collection = db["sold_items_daily_agg"]

    for agg in aggregations:
        try:
            doc = agg.to_dict_for_db()
            result = collection.update_one(
                {"_id": agg.id},
                {"$set": doc},
                upsert=True
            )

            if result.upserted_id:
                stats["inserted"] += 1
                logger.debug(f"Inserted: {agg.id}")
            else:
                stats["updated"] += 1
                logger.debug(f"Updated: {agg.id}")

        except Exception as e:
            stats["errors"] += 1
            logger.error(f"Failed to save {agg.id}: {e}")

    logger.info(
        f"Saved aggregations",
        extra={
            "inserted": stats["inserted"],
            "updated": stats["updated"],
            "errors": stats["errors"],
            "correlation_id": session_id
        }
    )

    return stats


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="SNKRDUNK Sold Items Scraper - Daily price aggregations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Dry run for Pokemon (validate without saving)
    python services/scrapers/snkrdunk_sold_scraper.py --game POKEMON --dry-run --headed

    # Production run for One Piece
    python services/scrapers/snkrdunk_sold_scraper.py --game ONE_PIECE --max-pages 10

    # All games
    python services/scrapers/snkrdunk_sold_scraper.py --game ALL --max-pages 5
        """
    )

    parser.add_argument(
        "--game",
        required=True,
        choices=["POKEMON", "YUGIOH", "ONE_PIECE", "ALL"],
        help="TCG game to scrape (or ALL for all games)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Maximum pages to scrape per game (default: 5)"
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

    # Session setup
    session_id = str(uuid.uuid4())[:8]
    scrape_date = date.today()
    headless = not args.headed

    # Determine games to scrape
    if args.game == "ALL":
        games_to_scrape = list(GAME_CONFIG.keys())
    else:
        games_to_scrape = [args.game]

    # Session logging
    logger.info("=" * 60)
    logger.info("SNKRDUNK SOLD ITEMS SCRAPER")
    logger.info("=" * 60)
    logger.info(
        "Starting scraper session",
        extra={
            "session_id": session_id,
            "games": games_to_scrape,
            "max_pages": args.max_pages,
            "dry_run": args.dry_run,
            "headless": headless,
            "scrape_date": scrape_date.isoformat(),
        }
    )

    all_aggregations = []
    total_items = 0

    try:
        with sync_playwright() as p:
            logger.info("Launching browser")
            browser = p.chromium.launch(headless=headless)
            context = create_stealth_context(browser)
            page = context.new_page()

            for game in games_to_scrape:
                logger.info(f"Processing game: {game}")

                # Scrape sold items
                sold_items = scrape_game_sold_items(
                    page=page,
                    game=game,
                    max_pages=args.max_pages,
                    session_id=session_id
                )

                total_items += len(sold_items)

                # Aggregate
                if sold_items:
                    aggregations = aggregate_sold_items(
                        sold_items=sold_items,
                        game=game,
                        scrape_date=scrape_date,
                        session_id=session_id
                    )
                    all_aggregations.extend(aggregations)

                # Delay between games
                if game != games_to_scrape[-1]:
                    delay = random.uniform(5, 10)
                    logger.info(f"Waiting {delay:.1f}s before next game")
                    time.sleep(delay)

            browser.close()

        # Save aggregations
        if all_aggregations:
            stats = save_aggregations(all_aggregations, args.dry_run, session_id)
        else:
            stats = {"inserted": 0, "updated": 0, "errors": 0}
            logger.warning("No aggregations to save")

        # Summary
        logger.info("=" * 60)
        logger.info("SCRAPER SESSION SUMMARY")
        logger.info("=" * 60)
        logger.info(
            "Session completed",
            extra={
                "session_id": session_id,
                "games_scraped": len(games_to_scrape),
                "total_items": total_items,
                "aggregations_created": len(all_aggregations),
                "inserted": stats["inserted"],
                "updated": stats["updated"],
                "errors": stats["errors"],
            }
        )

        # Console summary
        print("\n" + "=" * 60)
        print("SNKRDUNK SCRAPER SESSION SUMMARY")
        print("=" * 60)
        print(f"Session ID:         {session_id}")
        print(f"Scrape Date:        {scrape_date}")
        print(f"Games Scraped:      {', '.join(games_to_scrape)}")
        print(f"Total Items:        {total_items}")
        print(f"Aggregations:       {len(all_aggregations)}")
        print(f"Inserted:           {stats['inserted']}")
        print(f"Updated:            {stats['updated']}")
        print(f"Errors:             {stats['errors']}")
        print("=" * 60)

        if args.dry_run:
            print("\n✓ Dry run complete (no database writes)")
        else:
            print("\n✓ Database updated successfully")
            print("  View logs: tail -f logs/snkrdunk-scraper.log")

    except KeyboardInterrupt:
        logger.info("Scraper interrupted by user")
        print("\n\nScraper interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.critical("Fatal error", exc_info=True, extra={"session_id": session_id})
        print(f"\n\n❌ Fatal error: {e}")
        print("   Check logs: logs/snkrdunk-scraper.log")
        sys.exit(1)

    finally:
        if not args.dry_run:
            try:
                close_db()
                logger.debug("Database connection closed")
            except Exception:
                pass


if __name__ == "__main__":
    main()
