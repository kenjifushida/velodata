#!/usr/bin/env python3
"""
PayPay Flea Market URL POC - Test Item Page Selectors

This script tests the selectors for individual PayPay item pages.
Used to understand the page structure before building the full scraper.

Usage:
    source venv/bin/activate
    python services/scrapers/paypay_url_poc.py

Expected output:
    - Screenshots of the item page
    - HTML dumps for analysis
    - Console output of selector findings
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
# STEALTH CONFIGURATION
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
    screenshot_path = debug_dir / f"paypay_{name}_{timestamp}.png"
    page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"  Screenshot saved: {screenshot_path}")

    # Save HTML
    html_path = debug_dir / f"paypay_{name}_{timestamp}.html"
    html_content = page.content()
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"  HTML saved: {html_path}")

    return screenshot_path, html_path


# ============================================================================
# POC TESTS
# ============================================================================

def test_item_page_selectors(page: Page, url: str) -> dict:
    """
    Test all potential selectors on a PayPay item page.

    Args:
        page: Playwright page instance
        url: PayPay item URL to test

    Returns:
        Dictionary of findings
    """
    print("\n" + "=" * 60)
    print("TESTING PAYPAY ITEM PAGE SELECTORS")
    print("=" * 60)
    print(f"URL: {url}")

    findings = {
        "title": None,
        "price": None,
        "description": None,
        "images": [],
        "seller": None,
        "condition": None,
        "shipping": None,
        "category": None,
    }

    try:
        page.goto(url, wait_until="networkidle", timeout=60000)
        time.sleep(3)

        simulate_human_behavior(page)

        # Check if page loaded successfully
        title = page.title()
        print(f"\n  Page title: {title}")

        # Check for blocking
        body_text = page.locator('body').inner_text()
        blocking_phrases = [
            "アクセスが拒否",
            "Access Denied",
            "Bot detected",
        ]
        is_blocked = any(phrase in body_text for phrase in blocking_phrases)
        if is_blocked:
            print("  WARNING: Possible bot detection!")
            save_debug_artifacts(page, "item_blocked")
            return findings

        print("\n--- TESTING TITLE SELECTORS ---")
        title_selectors = [
            'h1',
            '[data-testid="item-title"]',
            '[class*="title"]',
            '[class*="Title"]',
            'meta[property="og:title"]',
            '.item-name',
            '.product-name',
            '.item-title',
        ]
        for selector in title_selectors:
            try:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    if selector.startswith('meta'):
                        text = elem.get_attribute('content')
                    else:
                        text = elem.inner_text(timeout=2000)
                    if text and len(text.strip()) > 0:
                        print(f"  ✓ {selector}: '{text[:80]}...'")
                        if not findings["title"]:
                            findings["title"] = {"selector": selector, "value": text.strip()}
            except Exception as e:
                pass

        print("\n--- TESTING PRICE SELECTORS ---")
        price_selectors = [
            '[data-testid="item-price"]',
            '[class*="price"]',
            '[class*="Price"]',
            '.item-price',
            '.product-price',
            'span:has-text("¥")',
            'div:has-text("¥")',
            'p:has-text("¥")',
        ]
        for selector in price_selectors:
            try:
                elems = page.locator(selector).all()
                for i, elem in enumerate(elems[:3]):  # Check first 3
                    text = elem.inner_text(timeout=2000)
                    if text and ('¥' in text or '円' in text):
                        print(f"  ✓ {selector}[{i}]: '{text[:50]}'")
                        if not findings["price"]:
                            findings["price"] = {"selector": selector, "value": text.strip()}
            except Exception as e:
                pass

        print("\n--- TESTING DESCRIPTION SELECTORS ---")
        desc_selectors = [
            '[data-testid="item-description"]',
            '[class*="description"]',
            '[class*="Description"]',
            '.item-description',
            '.product-description',
            'section[class*="description"]',
            'div[class*="detail"]',
        ]
        for selector in desc_selectors:
            try:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    text = elem.inner_text(timeout=2000)
                    if text and len(text.strip()) > 20:
                        print(f"  ✓ {selector}: '{text[:100]}...'")
                        if not findings["description"]:
                            findings["description"] = {"selector": selector, "value": text.strip()[:500]}
            except Exception as e:
                pass

        print("\n--- TESTING IMAGE SELECTORS ---")
        image_selectors = [
            'img[src*="paypay"]',
            'img[src*="yahoo"]',
            'img[class*="item"]',
            'img[class*="product"]',
            '.item-image img',
            '.product-image img',
            '[class*="gallery"] img',
            '[class*="slider"] img',
            'img[alt]',
        ]
        for selector in image_selectors:
            try:
                imgs = page.locator(selector).all()
                valid_imgs = []
                for img in imgs[:10]:
                    src = img.get_attribute('src')
                    if src and not src.startswith('data:') and 'blank' not in src.lower():
                        valid_imgs.append(src)
                if valid_imgs:
                    print(f"  ✓ {selector}: {len(valid_imgs)} images found")
                    for i, src in enumerate(valid_imgs[:3]):
                        print(f"      [{i}] {src[:80]}...")
                    if not findings["images"]:
                        findings["images"] = valid_imgs
            except Exception as e:
                pass

        print("\n--- TESTING SELLER SELECTORS ---")
        seller_selectors = [
            '[data-testid="seller"]',
            '[class*="seller"]',
            '[class*="Seller"]',
            '.seller-name',
            '.shop-name',
            'a[href*="/user/"]',
            'a[href*="/seller/"]',
        ]
        for selector in seller_selectors:
            try:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    text = elem.inner_text(timeout=2000)
                    if text and len(text.strip()) > 0:
                        print(f"  ✓ {selector}: '{text[:50]}'")
                        if not findings["seller"]:
                            findings["seller"] = {"selector": selector, "value": text.strip()}
            except Exception as e:
                pass

        print("\n--- TESTING CONDITION/STATUS SELECTORS ---")
        condition_selectors = [
            '[data-testid="item-condition"]',
            '[class*="condition"]',
            '[class*="Condition"]',
            '[class*="status"]',
            '[class*="Status"]',
            'span:has-text("新品")',
            'span:has-text("中古")',
            'span:has-text("未使用")',
            'div:has-text("商品の状態")',
        ]
        for selector in condition_selectors:
            try:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    text = elem.inner_text(timeout=2000)
                    if text and len(text.strip()) > 0:
                        print(f"  ✓ {selector}: '{text[:50]}'")
                        if not findings["condition"]:
                            findings["condition"] = {"selector": selector, "value": text.strip()}
            except Exception as e:
                pass

        print("\n--- TESTING SHIPPING SELECTORS ---")
        shipping_selectors = [
            '[data-testid="shipping"]',
            '[class*="shipping"]',
            '[class*="Shipping"]',
            '[class*="delivery"]',
            'span:has-text("送料")',
            'div:has-text("配送")',
        ]
        for selector in shipping_selectors:
            try:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    text = elem.inner_text(timeout=2000)
                    if text and len(text.strip()) > 0:
                        print(f"  ✓ {selector}: '{text[:50]}'")
                        if not findings["shipping"]:
                            findings["shipping"] = {"selector": selector, "value": text.strip()}
            except Exception as e:
                pass

        print("\n--- TESTING CATEGORY/BREADCRUMB SELECTORS ---")
        category_selectors = [
            'nav[aria-label*="breadcrumb"]',
            '[class*="breadcrumb"]',
            '[class*="Breadcrumb"]',
            '.category-path',
            'ol li a',
            'nav a',
        ]
        for selector in category_selectors:
            try:
                elems = page.locator(selector).all()
                if elems:
                    texts = [e.inner_text(timeout=1000) for e in elems[:5]]
                    texts = [t for t in texts if t and len(t.strip()) > 0]
                    if texts:
                        print(f"  ✓ {selector}: {texts[:5]}")
                        if not findings["category"]:
                            findings["category"] = {"selector": selector, "value": texts}
            except Exception as e:
                pass

        # Save artifacts
        save_debug_artifacts(page, "item_page")

        return findings

    except Exception as e:
        print(f"  ✗ Failed: {e}")
        save_debug_artifacts(page, "item_error")
        return findings


def analyze_dom_structure(page: Page):
    """Analyze the DOM structure to find data patterns."""
    print("\n" + "=" * 60)
    print("ANALYZING DOM STRUCTURE")
    print("=" * 60)

    try:
        # Look for data attributes
        data_attrs = page.evaluate("""
            () => {
                const elements = document.querySelectorAll('[data-testid], [data-qa], [data-cy]');
                return Array.from(elements).map(el => ({
                    tag: el.tagName,
                    testid: el.getAttribute('data-testid'),
                    qa: el.getAttribute('data-qa'),
                    cy: el.getAttribute('data-cy'),
                    className: el.className?.substring(0, 100)
                })).slice(0, 30);
            }
        """)

        if data_attrs:
            print("\n  Found data attributes:")
            for attr in data_attrs:
                print(f"    {attr['tag']}: testid={attr['testid']}, qa={attr['qa']}, cy={attr['cy']}")

        # Look for JSON-LD structured data
        json_ld = page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                return Array.from(scripts).map(s => {
                    try {
                        return JSON.parse(s.textContent);
                    } catch {
                        return null;
                    }
                }).filter(Boolean);
            }
        """)

        if json_ld:
            print("\n  Found JSON-LD structured data:")
            import json
            for ld in json_ld:
                print(f"    {json.dumps(ld, ensure_ascii=False, indent=4)[:500]}...")

        # Look for meta tags with product info
        meta_tags = page.evaluate("""
            () => {
                const metas = document.querySelectorAll('meta[property^="og:"], meta[property^="product:"], meta[name^="twitter:"]');
                return Array.from(metas).map(m => ({
                    property: m.getAttribute('property') || m.getAttribute('name'),
                    content: m.getAttribute('content')?.substring(0, 100)
                }));
            }
        """)

        if meta_tags:
            print("\n  Found meta tags:")
            for meta in meta_tags:
                print(f"    {meta['property']}: {meta['content']}")

    except Exception as e:
        print(f"  Error analyzing DOM: {e}")


def main():
    """Run the POC test on a specific PayPay item URL."""
    print("=" * 60)
    print("PAYPAY FLEA MARKET URL POC TEST")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Test URL
    test_url = "https://paypayfleamarket.yahoo.co.jp/item/z546568632"

    with sync_playwright() as p:
        print("\nLaunching browser (headed mode for debugging)...")
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )
        context = create_stealth_context(browser)
        page = context.new_page()

        try:
            # Run tests
            findings = test_item_page_selectors(page, test_url)

            # Analyze DOM structure
            analyze_dom_structure(page)

            # Print summary
            print("\n" + "=" * 60)
            print("POC RESULTS SUMMARY")
            print("=" * 60)
            print(f"  Title found:       {'✓' if findings['title'] else '✗'}")
            print(f"  Price found:       {'✓' if findings['price'] else '✗'}")
            print(f"  Description found: {'✓' if findings['description'] else '✗'}")
            print(f"  Images found:      {'✓' if findings['images'] else '✗'} ({len(findings['images'])} images)")
            print(f"  Seller found:      {'✓' if findings['seller'] else '✗'}")
            print(f"  Condition found:   {'✓' if findings['condition'] else '✗'}")
            print(f"  Shipping found:    {'✓' if findings['shipping'] else '✗'}")
            print(f"  Category found:    {'✓' if findings['category'] else '✗'}")
            print("=" * 60)

            if findings['title']:
                print(f"\n  Best title selector: {findings['title']['selector']}")
            if findings['price']:
                print(f"  Best price selector: {findings['price']['selector']}")
            if findings['description']:
                print(f"  Best description selector: {findings['description']['selector']}")

            print("\nBrowser will stay open for 30 seconds for manual inspection...")
            print("Press Ctrl+C to close earlier.")

            try:
                time.sleep(30)
            except KeyboardInterrupt:
                pass

        except KeyboardInterrupt:
            print("\n\nTest interrupted by user")

        finally:
            browser.close()

    return findings


if __name__ == "__main__":
    main()
