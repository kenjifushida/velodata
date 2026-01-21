#!/usr/bin/env python3
"""
SNKRDUNK Proof of Concept - Test Playwright Access

This script tests whether we can access SNKRDUNK's sold items/transaction data.

Goals:
1. Test if Playwright can load SNKRDUNK pages
2. Identify page structure for sold items (transaction history)
3. Understand condition ranks (PSA10, A, B, C, D) display
4. Check for anti-bot measures

Usage:
    source venv/bin/activate
    python services/scrapers/snkrdunk_poc.py

Expected output:
    - Screenshots of pages
    - HTML dumps for analysis
    - Console output of findings
"""
import sys
import time
import random
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext


# ============================================================================
# STEALTH CONFIGURATION (from yuyutei_seeder.py)
# ============================================================================

def create_stealth_context(browser: Browser) -> BrowserContext:
    """Create a stealth browser context with anti-bot measures."""
    viewport_width = random.randint(1366, 1920)
    viewport_height = random.randint(768, 1080)

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
        for _ in range(random.randint(2, 4)):
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            page.mouse.move(x, y)
            time.sleep(random.uniform(0.1, 0.3))

        # Scroll down
        scroll_amount = 0
        max_scroll = random.randint(500, 1000)
        while scroll_amount < max_scroll:
            scroll_step = random.randint(100, 300)
            page.evaluate(f"window.scrollBy(0, {scroll_step})")
            scroll_amount += scroll_step
            time.sleep(random.uniform(0.2, 0.5))

    except Exception as e:
        print(f"  Warning: Human behavior simulation failed: {e}")


def save_debug_artifacts(page: Page, name: str):
    """Save screenshot and HTML for debugging."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Create debug directory
    debug_dir = project_root / "debug"
    debug_dir.mkdir(exist_ok=True)

    # Save screenshot
    screenshot_path = debug_dir / f"snkrdunk_{name}_{timestamp}.png"
    page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"  Screenshot saved: {screenshot_path}")

    # Save HTML
    html_path = debug_dir / f"snkrdunk_{name}_{timestamp}.html"
    html_content = page.content()
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"  HTML saved: {html_path}")

    return screenshot_path, html_path


# ============================================================================
# POC TESTS
# ============================================================================

def test_homepage(page: Page) -> bool:
    """Test 1: Can we access the homepage?"""
    print("\n" + "=" * 60)
    print("TEST 1: Homepage Access")
    print("=" * 60)

    try:
        page.goto("https://snkrdunk.com/", wait_until="networkidle", timeout=30000)
        time.sleep(2)

        title = page.title()
        print(f"  Page title: {title}")

        # Check if we're actually blocked (not just analytics scripts)
        content = page.content()
        body_text = page.locator('body').inner_text()

        # Real blocking indicators in visible text
        blocking_phrases = [
            "アクセスが拒否",  # Access denied
            "ロボット",        # Robot
            "確認してください", # Please verify
            "Access Denied",
            "Bot detected",
        ]

        is_blocked = any(phrase in body_text for phrase in blocking_phrases)
        if is_blocked:
            print("  WARNING: Possible bot detection!")
            save_debug_artifacts(page, "homepage_blocked")
            return False

        save_debug_artifacts(page, "homepage")
        print("  ✓ Homepage loaded successfully")
        return True

    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def test_search_tcg(page: Page) -> bool:
    """Test 2: Can we search for TCG cards?"""
    print("\n" + "=" * 60)
    print("TEST 2: TCG Card Search (Pokemon)")
    print("=" * 60)

    try:
        # SNKRDUNK uses apparel-categories/25 for hobby items (trading cards)
        # brand_id=pokemon for Pokemon cards
        search_url = "https://snkrdunk.com/apparel-categories/25?department_name=hobby&brand_id=pokemon"

        print(f"  Navigating to: {search_url}")
        page.goto(search_url, wait_until="networkidle", timeout=30000)
        time.sleep(3)

        simulate_human_behavior(page)

        title = page.title()
        print(f"  Page title: {title}")

        # Look for card listings - updated selectors based on SNKRDUNK structure
        selectors_to_try = [
            'a[href*="/apparel-free-used-items/"]',  # Used item links
            'a[href*="/products/"]',                  # Product links
            '.product-card',
            '.card-item',
            '.item-card',
            '[class*="product"]',
            '[class*="item"]',
            'article',
            'li a[href*="item"]',
        ]

        found_items = False
        for selector in selectors_to_try:
            count = page.locator(selector).count()
            if count > 0:
                print(f"  Found {count} elements with selector: {selector}")
                found_items = True

        # Also check for price indicators
        content = page.content()
        if '円' in content:
            print("  Found price indicators (円)")

        save_debug_artifacts(page, "trading_cards")
        print("  ✓ Trading cards page loaded")
        return found_items or True  # Return True even if no items, page loaded

    except Exception as e:
        print(f"  ✗ Failed: {e}")
        save_debug_artifacts(page, "trading_cards_error")
        return False


def test_product_detail(page: Page) -> bool:
    """Test 3: Can we access a product detail page with price history?"""
    print("\n" + "=" * 60)
    print("TEST 3: Product Detail Page")
    print("=" * 60)

    try:
        # Try to find a product link and click it - updated selectors
        product_selectors = [
            'a[href*="/apparel-free-used-items/"]',  # Used items (TCG cards)
            'a[href*="/products/"]',                  # Products
            '.product-card a',
            '.item-card a',
        ]

        product_link = None
        for selector in product_selectors:
            links = page.locator(selector)
            if links.count() > 0:
                product_link = links.first
                href = product_link.get_attribute('href')
                print(f"  Found product link: {href}")
                break

        if product_link:
            product_link.click()
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(3)

            simulate_human_behavior(page)

            current_url = page.url
            print(f"  Current URL: {current_url}")

            # Look for price/transaction data
            price_selectors = [
                '[data-testid="price"]',
                '.price',
                '.transaction-history',
                '.sold-items',
                '.price-history',
                '[class*="price"]',
                '[class*="transaction"]',
            ]

            content = page.content()
            body_text = page.locator('body').inner_text()

            if '円' in content:
                print("  Found price indicator: ¥ (円)")

            for selector in price_selectors:
                count = page.locator(selector).count()
                if count > 0:
                    print(f"  Found {count} elements with selector: {selector}")

            # Look for condition ranks - SNKRDUNK uses these for TCG
            rank_keywords = ['PSA10', 'PSA 10', 'PSA9', 'PSA8', 'ランクA', 'ランクB', 'ランクC', 'ランクD',
                           'Aランク', 'Bランク', 'Cランク', 'Dランク', '美品', '良品', '並品']
            found_ranks = []
            for keyword in rank_keywords:
                if keyword in body_text:
                    found_ranks.append(keyword)

            if found_ranks:
                print(f"  Found condition ranks: {found_ranks}")

            # Look for transaction/sold indicators
            sold_keywords = ['取引', '売却', '販売', '成約', 'SOLD', '履歴']
            found_sold = []
            for keyword in sold_keywords:
                if keyword in body_text:
                    found_sold.append(keyword)

            if found_sold:
                print(f"  Found sold/transaction keywords: {found_sold}")

            save_debug_artifacts(page, "product_detail")
            print("  ✓ Product detail page loaded")
            return True
        else:
            print("  No product links found on current page")
            # Try direct navigation to a known product
            print("  Trying direct navigation to brands/pokemon...")
            page.goto("https://snkrdunk.com/brands/pokemon", wait_until="networkidle", timeout=30000)
            time.sleep(3)
            save_debug_artifacts(page, "brands_pokemon")
            return False

    except Exception as e:
        print(f"  ✗ Failed: {e}")
        save_debug_artifacts(page, "product_detail_error")
        return False


def test_sold_items_section(page: Page) -> bool:
    """Test 4: Can we find sold items / transaction history?"""
    print("\n" + "=" * 60)
    print("TEST 4: Sold Items / Transaction History")
    print("=" * 60)

    try:
        content = page.content()

        # Keywords that might indicate transaction history
        sold_keywords = [
            '取引履歴',      # Transaction history
            '売却済み',      # Sold
            '過去の取引',    # Past transactions
            '販売履歴',      # Sales history
            '成約',          # Closed deal
            'SOLD',
            'transaction',
            'history',
        ]

        found_keywords = []
        for keyword in sold_keywords:
            if keyword.lower() in content.lower():
                found_keywords.append(keyword)

        if found_keywords:
            print(f"  Found sold-related keywords: {found_keywords}")
        else:
            print("  No obvious sold items section found on current page")

        # Look for tabs or sections that might contain transaction data
        tab_selectors = [
            'button:has-text("取引")',
            'button:has-text("履歴")',
            'a:has-text("取引")',
            '[role="tab"]',
            '.tab',
            '.tabs',
        ]

        for selector in tab_selectors:
            try:
                count = page.locator(selector).count()
                if count > 0:
                    print(f"  Found {count} tab elements with selector: {selector}")
                    # Try clicking to see if it reveals transaction data
                    tab = page.locator(selector).first
                    tab_text = tab.inner_text()
                    print(f"    Tab text: {tab_text}")
            except:
                pass

        return len(found_keywords) > 0

    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def test_api_requests(page: Page) -> dict:
    """Test 5: Monitor network requests to find API endpoints."""
    print("\n" + "=" * 60)
    print("TEST 5: API Endpoint Discovery")
    print("=" * 60)

    api_endpoints = []

    def log_request(request):
        url = request.url
        if 'api' in url.lower() or 'graphql' in url.lower():
            api_endpoints.append({
                'url': url,
                'method': request.method,
            })

    page.on("request", log_request)

    try:
        # Reload the page to capture API calls
        page.reload(wait_until="networkidle", timeout=30000)
        time.sleep(3)

        # Scroll to trigger lazy loading
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 500)")
            time.sleep(1)

        if api_endpoints:
            print(f"  Found {len(api_endpoints)} API endpoints:")
            for ep in api_endpoints[:10]:  # Show first 10
                print(f"    {ep['method']} {ep['url'][:80]}...")
        else:
            print("  No obvious API endpoints detected")

        return {"endpoints": api_endpoints}

    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return {"endpoints": [], "error": str(e)}


def main():
    """Run all POC tests."""
    print("=" * 60)
    print("SNKRDUNK PLAYWRIGHT POC TEST")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")

    results = {
        "homepage": False,
        "search": False,
        "product_detail": False,
        "sold_items": False,
        "api_discovery": {},
    }

    with sync_playwright() as p:
        print("\nLaunching browser (headed mode for debugging)...")
        browser = p.chromium.launch(headless=False)  # Headed for POC
        context = create_stealth_context(browser)
        page = context.new_page()

        try:
            # Run tests
            results["homepage"] = test_homepage(page)

            if results["homepage"]:
                time.sleep(random.uniform(2, 4))
                results["search"] = test_search_tcg(page)

            if results["search"]:
                time.sleep(random.uniform(2, 4))
                results["product_detail"] = test_product_detail(page)

            if results["product_detail"]:
                time.sleep(random.uniform(1, 2))
                results["sold_items"] = test_sold_items_section(page)
                results["api_discovery"] = test_api_requests(page)

        except KeyboardInterrupt:
            print("\n\nTest interrupted by user")

        finally:
            # Keep browser open for manual inspection
            print("\n" + "=" * 60)
            print("POC RESULTS SUMMARY")
            print("=" * 60)
            print(f"  Homepage Access:     {'✓' if results['homepage'] else '✗'}")
            print(f"  TCG Search:          {'✓' if results['search'] else '✗'}")
            print(f"  Product Detail:      {'✓' if results['product_detail'] else '✗'}")
            print(f"  Sold Items Found:    {'✓' if results['sold_items'] else '✗'}")
            print(f"  API Endpoints Found: {len(results['api_discovery'].get('endpoints', []))}")
            print("=" * 60)

            print("\nBrowser will stay open for 30 seconds for manual inspection...")
            print("Press Ctrl+C to close earlier.")

            try:
                time.sleep(30)
            except KeyboardInterrupt:
                pass

            browser.close()

    return results


if __name__ == "__main__":
    main()
