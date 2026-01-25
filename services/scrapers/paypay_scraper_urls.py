#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PayPay Flea Market URL Scraper - Scrapes specific item URLs from a file.

This scraper reads PayPay Flea Market item URLs from a text file and scrapes
detailed product information from each page. Useful for targeted scraping of
specific items identified for potential arbitrage opportunities.

Architecture:
    - Strategy Pattern for niche-specific attribute extraction
    - JSON-LD structured data extraction (primary source)
    - Fallback DOM extraction when JSON-LD is unavailable
    - Factory functions for type-safe MarketListing creation

Supported Niches:
    - TCG: Trading Card Games (Pokemon, Yu-Gi-Oh!, One Piece, Magic, etc.)
    - WATCH: Luxury and vintage wristwatches
    - CAMERA_GEAR: Digital cameras, lenses, and photography equipment
    - LUXURY_ITEM: Designer bags, wallets, and accessories
    - VIDEOGAME: Game consoles and video games
    - STATIONARY: Writing utensils, fountain pens, and office supplies
    - COLLECTION_FIGURES: Anime figures, collectible figurines, and model kits

Usage:
    # Create a URL file first
    mkdir -p data
    echo "https://paypayfleamarket.yahoo.co.jp/item/z546568632" > data/paypay_urls.txt

    # Dry run - validate without database writes (uses data/paypay_urls.txt by default)
    python paypay_scraper_urls.py --niche TCG --dry-run --headed

    # Live run - save to market_listings collection
    python paypay_scraper_urls.py --niche TCG

    # Custom URL file (optional)
    python paypay_scraper_urls.py --niche WATCH --urls data/watch_urls.txt

Examples:
    # Scrape TCG cards (uses default file: data/paypay_urls.txt)
    python services/scrapers/paypay_scraper_urls.py --niche TCG --dry-run --headed

    # Scrape with custom URL file
    python services/scrapers/paypay_scraper_urls.py --niche WATCH --urls data/watch_urls.txt --dry-run
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
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Literal, Any
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
    detect_tcg_game,
    extract_tcg_card_info,
    ALL_GAME_CONFIGS,
)

# Initialize logger for this service
logger = get_logger("paypay-url-scraper")


# ============================================================================
# CONSTANTS
# ============================================================================

BASE_URL = "https://paypayfleamarket.yahoo.co.jp"

# Default URL file location (relative to project root)
DEFAULT_URL_FILE = PROJECT_ROOT / "data" / "paypay_urls.txt"

# Niche types supported
NicheType = Literal[
    "TCG", "WATCH", "CAMERA_GEAR", "LUXURY_ITEM",
    "VIDEOGAME", "STATIONARY", "COLLECTION_FIGURES"
]


# ============================================================================
# ATTRIBUTE EXTRACTORS (Strategy Pattern)
# ============================================================================

class AttributeExtractor(ABC):
    """
    Abstract base class for niche-specific attribute extraction.

    Each niche has unique fields that need to be extracted from
    the product title and description. This pattern allows for
    extensible extraction logic without modifying core scraping code.
    """

    @abstractmethod
    def extract(
        self,
        title: str,
        description: Optional[str],
        json_ld: Optional[Dict],
    ) -> Dict[str, Any]:
        """
        Extract niche-specific attributes from product data.

        Args:
            title: Product title
            description: Product description (may be None)
            json_ld: JSON-LD structured data (may be None)

        Returns:
            Dictionary of extracted attributes
        """
        pass


class TCGAttributeExtractor(AttributeExtractor):
    """
    Extract TCG card attributes from product data.

    Extracts:
        - game: TCG game type (POKEMON, YUGIOH, ONE_PIECE, etc.)
        - set_code: Set/expansion code
        - card_number: Card number within set
        - rarity: Card rarity
        - is_graded: Whether card is graded
        - grading_company: PSA, BGS, CGC, etc.
        - grade: Numeric grade (10, 9.5, 9, etc.)
        - language: Card language (JP, EN, etc.)
    """

    def extract(
        self,
        title: str,
        description: Optional[str],
        json_ld: Optional[Dict],
    ) -> Dict[str, Any]:
        """Extract TCG card attributes using centralized detector."""
        # Use centralized TCG card info extraction
        card_info = extract_tcg_card_info(title)

        # Add raw title for debugging
        card_info["raw_title"] = title

        # Try to extract additional info from description
        if description:
            card_info["raw_description"] = description[:1000]

            # Extract PSA certificate number if present
            cert_match = re.search(r'(?:カード番号|Cert(?:ification)?[:\s#]*|#)\s*(\d{8,})', description)
            if cert_match:
                card_info["cert_number"] = cert_match.group(1)

        logger.debug(
            "Extracted TCG attributes",
            extra={
                "game": card_info.get("game"),
                "is_graded": card_info.get("is_graded"),
                "grade": card_info.get("grade"),
            }
        )

        return card_info


class WatchAttributeExtractor(AttributeExtractor):
    """
    Extract watch attributes from product data.

    Extracts:
        - brand: Manufacturer (Rolex, Omega, Seiko, etc.)
        - model: Model name
        - reference_number: Official reference number
        - case_material: Steel, Gold, Titanium, etc.
        - case_size: Diameter in mm
        - movement: Automatic, Quartz, Manual
        - box_included: Original box present
        - papers_included: Original papers present
    """

    # Major watch brands for detection
    WATCH_BRANDS = [
        "Rolex", "ロレックス",
        "Omega", "オメガ",
        "Seiko", "セイコー",
        "Casio", "カシオ",
        "Grand Seiko", "グランドセイコー",
        "Patek Philippe", "パテック フィリップ",
        "Audemars Piguet", "オーデマピゲ",
        "Tudor", "チューダー",
        "IWC",
        "Cartier", "カルティエ",
        "Breitling", "ブライトリング",
        "Tag Heuer", "タグホイヤー",
        "Panerai", "パネライ",
        "Hublot", "ウブロ",
    ]

    def extract(
        self,
        title: str,
        description: Optional[str],
        json_ld: Optional[Dict],
    ) -> Dict[str, Any]:
        """Extract watch attributes from product data."""
        attributes: Dict[str, Any] = {"raw_title": title}
        text = f"{title} {description or ''}"

        # Extract brand
        for brand in self.WATCH_BRANDS:
            if brand.lower() in text.lower():
                attributes["brand"] = brand.split("/")[0].strip()
                break

        # Extract reference number (patterns like 116610, 326934, etc.)
        ref_match = re.search(r'\b(\d{5,6}[A-Z]{0,3})\b', text)
        if ref_match:
            attributes["reference_number"] = ref_match.group(1)

        # Extract case size (e.g., 40mm, 42mm)
        size_match = re.search(r'(\d{2,3})\s*mm', text, re.IGNORECASE)
        if size_match:
            attributes["case_size"] = f"{size_match.group(1)}mm"

        # Check for box and papers
        attributes["box_included"] = any(
            term in text for term in ["箱付", "箱あり", "BOX付", "with box", "付属品完備"]
        )
        attributes["papers_included"] = any(
            term in text for term in ["保証書", "ギャランティ", "papers", "warranty"]
        )

        # Extract movement type
        if any(term in text for term in ["自動巻", "オートマティック", "automatic"]):
            attributes["movement"] = "AUTOMATIC"
        elif any(term in text for term in ["クォーツ", "quartz", "電池"]):
            attributes["movement"] = "QUARTZ"
        elif any(term in text for term in ["手巻", "manual"]):
            attributes["movement"] = "MANUAL"

        if description:
            attributes["raw_description"] = description[:1000]

        return attributes


class CameraGearAttributeExtractor(AttributeExtractor):
    """
    Extract camera gear attributes from product data.

    Extracts:
        - brand: Manufacturer (Canon, Nikon, Sony, etc.)
        - model_number: Model name/number
        - subcategory: CAMERA, LENS, VIDEO_CAMERA, etc.
        - mount: Lens mount type
        - sensor_size: Full-frame, APS-C, etc.
    """

    CAMERA_BRANDS = [
        "Canon", "キヤノン",
        "Nikon", "ニコン",
        "Sony", "ソニー",
        "Fujifilm", "富士フイルム",
        "Panasonic", "パナソニック",
        "Olympus", "オリンパス",
        "Leica", "ライカ",
        "Sigma", "シグマ",
        "Tamron", "タムロン",
    ]

    SUBCATEGORY_PATTERNS = {
        "CAMERA": ["カメラ", "一眼", "ミラーレス", "camera", "body"],
        "LENS": ["レンズ", "lens", "mm f/", "mm F"],
        "VIDEO_CAMERA": ["ビデオ", "video", "camcorder"],
    }

    def extract(
        self,
        title: str,
        description: Optional[str],
        json_ld: Optional[Dict],
    ) -> Dict[str, Any]:
        """Extract camera gear attributes from product data."""
        attributes: Dict[str, Any] = {"raw_title": title}
        text = f"{title} {description or ''}"

        # Extract brand
        for brand in self.CAMERA_BRANDS:
            if brand.lower() in text.lower():
                attributes["brand"] = brand.split("/")[0].strip()
                break

        # Detect subcategory
        for subcat, patterns in self.SUBCATEGORY_PATTERNS.items():
            if any(p.lower() in text.lower() for p in patterns):
                attributes["subcategory"] = subcat
                break

        # Extract model number (patterns like EOS R5, Z9, A7R IV)
        model_patterns = [
            r'\b(EOS\s*R?\d*[A-Z]*)\b',
            r'\b(Z\s*\d+[A-Z]*)\b',
            r'\b(A\d+[RSIV]*)\b',
            r'\b(X-[A-Z]\d+)\b',
            r'\b(GH\d+)\b',
        ]
        for pattern in model_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                attributes["model_number"] = match.group(1).upper()
                break

        # Extract lens specs (e.g., 24-70mm f/2.8)
        lens_match = re.search(r'(\d+(?:-\d+)?)\s*mm\s*[fF]/?\s*([\d.]+)', text)
        if lens_match:
            attributes["focal_length"] = f"{lens_match.group(1)}mm"
            attributes["aperture"] = f"f/{lens_match.group(2)}"

        if description:
            attributes["raw_description"] = description[:1000]

        return attributes


class LuxuryItemAttributeExtractor(AttributeExtractor):
    """Extract luxury item (bags, wallets) attributes."""

    LUXURY_BRANDS = [
        "Louis Vuitton", "ルイヴィトン",
        "Gucci", "グッチ",
        "Chanel", "シャネル",
        "Hermes", "エルメス",
        "Prada", "プラダ",
        "Dior", "ディオール",
        "Fendi", "フェンディ",
        "Bottega Veneta", "ボッテガ ヴェネタ",
        "Celine", "セリーヌ",
        "Balenciaga", "バレンシアガ",
    ]

    def extract(
        self,
        title: str,
        description: Optional[str],
        json_ld: Optional[Dict],
    ) -> Dict[str, Any]:
        """Extract luxury item attributes."""
        attributes: Dict[str, Any] = {"raw_title": title}
        text = f"{title} {description or ''}"

        # Extract brand
        for brand in self.LUXURY_BRANDS:
            if brand.lower() in text.lower():
                attributes["brand"] = brand.split("/")[0].strip()
                break

        # Detect item type
        if any(term in text for term in ["バッグ", "bag", "トート", "ショルダー"]):
            attributes["item_type"] = "BAG"
        elif any(term in text for term in ["財布", "wallet", "長財布", "二つ折り"]):
            attributes["item_type"] = "WALLET"
        elif any(term in text for term in ["ベルト", "belt"]):
            attributes["item_type"] = "BELT"

        if description:
            attributes["raw_description"] = description[:1000]

        return attributes


class VideogameAttributeExtractor(AttributeExtractor):
    """Extract videogame/console attributes."""

    def extract(
        self,
        title: str,
        description: Optional[str],
        json_ld: Optional[Dict],
    ) -> Dict[str, Any]:
        """Extract videogame attributes."""
        attributes: Dict[str, Any] = {"raw_title": title}
        text = f"{title} {description or ''}"

        # Detect platform
        platforms = {
            "PLAYSTATION_5": ["PS5", "PlayStation 5", "プレイステーション5"],
            "PLAYSTATION_4": ["PS4", "PlayStation 4", "プレイステーション4"],
            "NINTENDO_SWITCH": ["Switch", "スイッチ", "Nintendo Switch"],
            "XBOX": ["Xbox", "XBOX"],
        }

        for platform, keywords in platforms.items():
            if any(kw.lower() in text.lower() for kw in keywords):
                attributes["platform"] = platform
                break

        if description:
            attributes["raw_description"] = description[:1000]

        return attributes


class StationaryAttributeExtractor(AttributeExtractor):
    """Extract stationary/writing instrument attributes."""

    def extract(
        self,
        title: str,
        description: Optional[str],
        json_ld: Optional[Dict],
    ) -> Dict[str, Any]:
        """Extract stationary attributes."""
        attributes: Dict[str, Any] = {"raw_title": title}
        text = f"{title} {description or ''}"

        # Detect pen brands
        pen_brands = [
            "Montblanc", "モンブラン",
            "Pelikan", "ペリカン",
            "Parker", "パーカー",
            "Pilot", "パイロット",
            "Sailor", "セーラー",
            "Platinum", "プラチナ",
        ]

        for brand in pen_brands:
            if brand.lower() in text.lower():
                attributes["brand"] = brand.split("/")[0].strip()
                break

        # Detect pen type
        if any(term in text for term in ["万年筆", "fountain", "FP"]):
            attributes["pen_type"] = "FOUNTAIN_PEN"
        elif any(term in text for term in ["ボールペン", "ballpoint", "BP"]):
            attributes["pen_type"] = "BALLPOINT"
        elif any(term in text for term in ["ローラーボール", "rollerball"]):
            attributes["pen_type"] = "ROLLERBALL"

        if description:
            attributes["raw_description"] = description[:1000]

        return attributes


class CollectionFiguresAttributeExtractor(AttributeExtractor):
    """Extract collectible figure attributes."""

    def extract(
        self,
        title: str,
        description: Optional[str],
        json_ld: Optional[Dict],
    ) -> Dict[str, Any]:
        """Extract figure attributes."""
        attributes: Dict[str, Any] = {"raw_title": title}
        text = f"{title} {description or ''}"

        # Detect figure types
        if any(term in text for term in ["フィギュア", "figure", "Figure"]):
            attributes["item_type"] = "FIGURE"
        elif any(term in text for term in ["プラモデル", "ガンプラ", "gundam", "model kit"]):
            attributes["item_type"] = "MODEL_KIT"
        elif any(term in text for term in ["ねんどろいど", "nendoroid"]):
            attributes["item_type"] = "NENDOROID"
        elif any(term in text for term in ["figma"]):
            attributes["item_type"] = "FIGMA"

        # Detect manufacturer
        figure_makers = [
            "Good Smile Company", "グッドスマイルカンパニー",
            "Bandai", "バンダイ",
            "Kotobukiya", "コトブキヤ",
            "Alter", "アルター",
            "Max Factory", "マックスファクトリー",
        ]

        for maker in figure_makers:
            if maker.lower() in text.lower():
                attributes["manufacturer"] = maker.split("/")[0].strip()
                break

        # Check if new/unopened
        attributes["is_unopened"] = any(
            term in text for term in ["未開封", "新品", "unopened", "sealed"]
        )

        if description:
            attributes["raw_description"] = description[:1000]

        return attributes


# Extractor registry (Strategy Pattern)
ATTRIBUTE_EXTRACTORS: Dict[str, AttributeExtractor] = {
    "TCG": TCGAttributeExtractor(),
    "WATCH": WatchAttributeExtractor(),
    "CAMERA_GEAR": CameraGearAttributeExtractor(),
    "LUXURY_ITEM": LuxuryItemAttributeExtractor(),
    "VIDEOGAME": VideogameAttributeExtractor(),
    "STATIONARY": StationaryAttributeExtractor(),
    "COLLECTION_FIGURES": CollectionFiguresAttributeExtractor(),
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
    viewport_width = random.randint(1366, 1920)
    viewport_height = random.randint(768, 1080)

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
    Simulate human-like behavior on the page.

    Args:
        page: Playwright page instance
        correlation_id: Session correlation ID for logging
    """
    try:
        # Random mouse movements
        for _ in range(random.randint(2, 3)):
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            page.mouse.move(x, y)
            time.sleep(random.uniform(0.1, 0.2))

        # Scroll down slightly
        page.evaluate("window.scrollBy(0, 300)")
        time.sleep(random.uniform(0.3, 0.5))

    except Exception as e:
        logger.warning(
            "Failed to simulate human behavior",
            extra={"correlation_id": correlation_id, "error": str(e)}
        )


# ============================================================================
# DATA EXTRACTION
# ============================================================================

def extract_json_ld(page: Page) -> Optional[Dict]:
    """
    Extract JSON-LD structured data from page.

    PayPay item pages contain Product schema.org data which is the most
    reliable source for product information.

    Args:
        page: Playwright page instance

    Returns:
        Parsed JSON-LD data or None if not found
    """
    try:
        json_ld_data = page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                for (const script of scripts) {
                    try {
                        const data = JSON.parse(script.textContent);
                        if (data['@type'] === 'Product') {
                            return data;
                        }
                    } catch {}
                }
                return null;
            }
        """)
        return json_ld_data
    except Exception:
        return None


def extract_meta_tags(page: Page) -> Dict[str, str]:
    """
    Extract Open Graph and Twitter meta tags.

    Args:
        page: Playwright page instance

    Returns:
        Dictionary of meta tag values
    """
    try:
        return page.evaluate("""
            () => {
                const metas = {};
                const tags = document.querySelectorAll('meta[property^="og:"], meta[name^="twitter:"]');
                for (const tag of tags) {
                    const key = tag.getAttribute('property') || tag.getAttribute('name');
                    metas[key] = tag.getAttribute('content');
                }
                return metas;
            }
        """)
    except Exception:
        return {}


def extract_product_data(
    page: Page,
    url: str,
    niche_type: NicheType,
    correlation_id: str
) -> Optional[Dict]:
    """
    Extract product data from a PayPay item page.

    Uses a multi-source extraction strategy:
    1. JSON-LD structured data (primary - most reliable)
    2. Open Graph meta tags (fallback)
    3. DOM element extraction (last resort)

    Args:
        page: Playwright page instance
        url: Item URL being scraped
        niche_type: Product niche type for attribute extraction
        correlation_id: Session correlation ID

    Returns:
        Dictionary with product data or None if extraction fails
    """
    try:
        # Extract external ID from URL
        id_match = re.search(r'/item/([a-zA-Z0-9_-]+)', url)
        if not id_match:
            logger.warning(
                "Could not extract item ID from URL",
                extra={"url": url, "correlation_id": correlation_id}
            )
            return None

        external_id = id_match.group(1)

        # Navigate to page
        response = page.goto(url, wait_until='networkidle', timeout=60000)

        if not response or not response.ok:
            logger.error(
                "Failed to load page",
                extra={
                    "url": url,
                    "status": response.status if response else "No response",
                    "correlation_id": correlation_id
                }
            )
            return None

        # Brief delay for dynamic content
        time.sleep(random.uniform(1.5, 2.5))
        simulate_human_behavior(page, correlation_id)

        # === PRIMARY: JSON-LD Extraction (for title, description, price) ===
        json_ld = extract_json_ld(page)
        meta_tags = extract_meta_tags(page)

        title = None
        description = None
        price_jpy = None
        image_urls = []

        if json_ld:
            logger.debug(
                "Found JSON-LD structured data",
                extra={"external_id": external_id, "correlation_id": correlation_id}
            )
            title = json_ld.get("name")
            description = json_ld.get("description")

            # Extract price from JSON-LD offers
            offers = json_ld.get("offers", {})
            if isinstance(offers, dict):
                price_str = offers.get("price")
                if price_str:
                    try:
                        price_jpy = int(float(str(price_str).replace(",", "")))
                    except ValueError:
                        pass

        # === FALLBACK: Meta Tags (for title, description) ===
        if not title:
            title = meta_tags.get("og:title", "").split("｜")[0].strip()

        if not description:
            description = meta_tags.get("og:description")

        # === FALLBACK: DOM Extraction (for title, price) ===
        if not title:
            try:
                h1 = page.locator('h1').first
                if h1.count() > 0:
                    title = h1.inner_text(timeout=2000).strip()
            except Exception:
                pass

        if not price_jpy:
            try:
                price_elem = page.locator('[class*="Price"]').first
                if price_elem.count() > 0:
                    price_text = price_elem.inner_text(timeout=2000)
                    price_match = re.search(r'[\d,]+', price_text.replace(',', ''))
                    if price_match:
                        price_jpy = int(price_match.group(0).replace(',', ''))
            except Exception:
                pass

        # === IMAGE EXTRACTION (Always use DOM - .slick-list contains all product images) ===
        try:
            # Primary: Get all product images from the slick slider
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
                    f"Extracted {len(image_urls)} images from .slick-list",
                    extra={"external_id": external_id, "correlation_id": correlation_id}
                )
        except Exception as e:
            logger.warning(
                "Failed to extract images from .slick-list",
                extra={"error": str(e), "correlation_id": correlation_id}
            )

        # Fallback: Try other slider selectors if .slick-list failed
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

        # Final fallback: Use JSON-LD or meta tag image
        if not image_urls:
            if json_ld and json_ld.get("image"):
                img = json_ld["image"]
                if isinstance(img, str):
                    image_urls.append(img)
                elif isinstance(img, list):
                    image_urls.extend(img[:10])
            elif meta_tags.get("og:image"):
                image_urls.append(meta_tags["og:image"])

        # === Validation ===
        if not title:
            logger.warning(
                "Could not extract title",
                extra={"url": url, "correlation_id": correlation_id}
            )
            title = f"PayPay Item {external_id}"

        if not price_jpy:
            logger.warning(
                "Could not extract price",
                extra={"url": url, "correlation_id": correlation_id}
            )
            return None  # Price is required

        # === Extract Niche-Specific Attributes ===
        extractor = ATTRIBUTE_EXTRACTORS.get(niche_type)
        if extractor:
            attributes = extractor.extract(title, description, json_ld)
        else:
            attributes = {"raw_title": title}
            if description:
                attributes["raw_description"] = description[:1000]

        # Extract shipping info
        try:
            shipping_elem = page.locator('[class*="Shipping"], span:has-text("送料")').first
            if shipping_elem.count() > 0:
                shipping_text = shipping_elem.inner_text(timeout=2000)
                attributes["shipping_info"] = shipping_text.strip()
        except Exception:
            pass

        # Extract seller info
        try:
            seller_elem = page.locator('a[href*="/user/"]').first
            if seller_elem.count() > 0:
                seller_text = seller_elem.inner_text(timeout=2000)
                # Clean up seller text (remove ratings, etc.)
                seller_name = seller_text.split('\n')[0].strip()
                attributes["seller_name"] = seller_name
        except Exception:
            pass

        return {
            "external_id": external_id,
            "niche_type": niche_type,
            "title": title,
            "price_jpy": price_jpy,
            "url": url,
            "image_urls": image_urls,
            "attributes": attributes,
            "scrape_session_id": correlation_id,
        }

    except Exception as e:
        logger.error(
            "Failed to extract product data",
            exc_info=True,
            extra={"url": url, "correlation_id": correlation_id}
        )
        return None


# ============================================================================
# URL FILE HANDLING
# ============================================================================

def load_urls_from_file(file_path: Path) -> List[str]:
    """
    Load PayPay item URLs from a text file.

    File format:
        - One URL per line
        - Lines starting with # are comments
        - Empty lines are ignored
        - URLs must match: https://paypayfleamarket.yahoo.co.jp/item/{id}

    Args:
        file_path: Path to the URL file

    Returns:
        List of valid PayPay item URLs

    Raises:
        FileNotFoundError: If the file doesn't exist
    """
    if not file_path.exists():
        raise FileNotFoundError(f"URL file not found: {file_path}")

    urls = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Validate PayPay URL format
            if not re.match(r'https://paypayfleamarket\.yahoo\.co\.jp/item/[a-zA-Z0-9_-]+', line):
                logger.warning(
                    f"Invalid URL format on line {line_num}, skipping: {line[:50]}"
                )
                continue

            urls.append(line)

    return urls


# ============================================================================
# SCRAPING ORCHESTRATION
# ============================================================================

@log_execution_time(logger)
def scrape_urls(
    urls: List[str],
    niche_type: NicheType,
    headless: bool = True,
    session_id: Optional[str] = None
) -> List[Dict]:
    """
    Scrape product data from a list of PayPay item URLs.

    Args:
        urls: List of PayPay item URLs to scrape
        niche_type: Product niche type
        headless: Whether to run browser in headless mode
        session_id: Scraping session correlation ID

    Returns:
        List of scraped product dictionaries
    """
    correlation_id = session_id or str(uuid.uuid4())[:8]
    logger.info(
        "Starting URL scrape session",
        extra={
            "url_count": len(urls),
            "niche_type": niche_type,
            "headless": headless,
            "correlation_id": correlation_id
        }
    )

    products = []

    with sync_playwright() as p:
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
            context = create_stealth_context(browser)
            page = context.new_page()

            for idx, url in enumerate(urls, 1):
                logger.info(
                    f"Scraping URL {idx}/{len(urls)}",
                    extra={"url": url[:80], "correlation_id": correlation_id}
                )

                try:
                    product_data = extract_product_data(
                        page, url, niche_type, correlation_id
                    )

                    if product_data:
                        products.append(product_data)
                        logger.debug(
                            f"Successfully extracted: {product_data['external_id']}",
                            extra={"correlation_id": correlation_id}
                        )
                    else:
                        logger.warning(
                            f"Failed to extract data from URL",
                            extra={"url": url, "correlation_id": correlation_id}
                        )

                except Exception as e:
                    logger.error(
                        f"Error scraping URL",
                        exc_info=True,
                        extra={"url": url, "correlation_id": correlation_id}
                    )

                # Rate limiting between requests
                if idx < len(urls):
                    delay = random.uniform(2, 4)
                    time.sleep(delay)

        finally:
            browser.close()

    logger.info(
        "URL scrape session complete",
        extra={
            "total_urls": len(urls),
            "successful": len(products),
            "correlation_id": correlation_id
        }
    )

    return products


# ============================================================================
# DATABASE INSERTION
# ============================================================================

@log_execution_time(logger)
def insert_market_listings(products_data: List[Dict], dry_run: bool = False) -> int:
    """
    Insert scraped products into MongoDB market_listings collection.

    Args:
        products_data: List of scraped product dictionaries
        dry_run: If True, validate but don't insert to database

    Returns:
        Number of products successfully inserted
    """
    if dry_run:
        logger.info(
            f"DRY RUN MODE: Validating {len(products_data)} listings",
            extra={"dry_run": True}
        )
    else:
        logger.info(f"Inserting {len(products_data)} listings to market_listings")

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
                # Print formatted output
                print(f"\n{'='*70}")
                print(f"Listing ID: {listing.id}")
                print(f"Niche Type: {listing.niche_type}")

                attrs = listing.attributes

                # Show TCG-specific info
                if listing.niche_type == "TCG" and attrs.get("game"):
                    game = attrs.get("game")
                    try:
                        tcg_game = TCGGame(game)
                        config = ALL_GAME_CONFIGS.get(tcg_game)
                        game_display = config.display_name_en if config else game
                    except ValueError:
                        game_display = game
                    print(f"TCG Game:   {game_display}")
                    if attrs.get("is_graded"):
                        print(f"Graded:     Yes ({attrs.get('grading_company')} {attrs.get('grade')})")
                    if attrs.get("set_code"):
                        print(f"Set Code:   {attrs.get('set_code')}")

                # Show brand info for other niches
                if attrs.get("brand"):
                    print(f"Brand:      {attrs['brand']}")

                print(f"Title:      {listing.title[:60]}...")
                print(f"Price:      ¥{listing.price_jpy:,}")
                print(f"URL:        {listing.url}")
                if listing.image_urls:
                    print(f"Images:     {len(listing.image_urls)} image(s)")
                print(f"{'='*70}")
                inserted_count += 1

            else:
                # Check if listing already exists
                existing = collection.find_one({
                    "$or": [
                        {"_id": listing.id},
                        {"url": str(listing.url)}
                    ]
                })

                if existing:
                    logger.debug(
                        f"Listing already exists, skipping: {listing.id}",
                        extra={"listing_id": listing.id}
                    )
                    skipped_count += 1
                else:
                    collection.insert_one(listing.to_dict_for_db())
                    logger.debug(
                        f"Inserted listing: {listing.id}",
                        extra={"listing_id": listing.id}
                    )
                    inserted_count += 1

        except ValidationError as e:
            error_count += 1
            logger.error(
                "Validation failed for listing",
                exc_info=True,
                extra={"product": product.get('title', 'Unknown')[:50]}
            )
        except Exception as e:
            error_count += 1
            logger.error(
                "Error inserting listing",
                exc_info=True,
                extra={"product": product.get('title', 'Unknown')[:50]}
            )

    if dry_run:
        logger.info(
            f"DRY RUN COMPLETE: {inserted_count} validated, {error_count} errors",
            extra={"validated": inserted_count, "errors": error_count}
        )
    else:
        logger.info(
            "Insertion completed",
            extra={
                "inserted": inserted_count,
                "skipped": skipped_count,
                "errors": error_count,
            }
        )

    return inserted_count


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="PayPay Flea Market URL Scraper - Scrapes specific item URLs from a file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run with default URL file (data/paypay_urls.txt)
  python paypay_scraper_urls.py --niche TCG --dry-run --headed

  # Custom URL file (optional)
  python paypay_scraper_urls.py --niche WATCH --urls data/watch_urls.txt --dry-run

  # Live run - save to database
  python paypay_scraper_urls.py --niche TCG

URL File Format (data/paypay_urls.txt):
  # Comments start with #
  https://paypayfleamarket.yahoo.co.jp/item/z546568632
  https://paypayfleamarket.yahoo.co.jp/item/abc123def
        """
    )

    parser.add_argument(
        "--niche",
        required=True,
        choices=["TCG", "WATCH", "CAMERA_GEAR", "LUXURY_ITEM", "VIDEOGAME", "STATIONARY", "COLLECTION_FIGURES"],
        help="Product niche type (required)"
    )
    parser.add_argument(
        "--urls",
        type=str,
        default=None,
        help=f"Path to URL file (optional, default: data/paypay_urls.txt)"
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

    # Determine URL file path
    if args.urls:
        url_file = Path(args.urls)
    else:
        url_file = DEFAULT_URL_FILE

    # Session setup
    session_id = str(uuid.uuid4())[:8]
    logger.info("=" * 60)
    logger.info("VELODATA - PAYPAY URL SCRAPER")
    logger.info("=" * 60)
    logger.info(
        "Starting scraper session",
        extra={
            "session_id": session_id,
            "niche_type": args.niche,
            "url_file": str(url_file),
            "headless": not args.headed,
            "dry_run": args.dry_run,
        }
    )

    total_scraped = 0
    total_inserted = 0

    try:
        # Load URLs from file
        urls = load_urls_from_file(url_file)

        if not urls:
            logger.warning("No valid URLs found in file", extra={"file": str(url_file)})
            return

        logger.info(
            f"Loaded {len(urls)} URLs from file",
            extra={"file": str(url_file), "session_id": session_id}
        )

        # Scrape URLs
        products_data = scrape_urls(
            urls=urls,
            niche_type=args.niche,
            headless=not args.headed,
            session_id=session_id
        )

        total_scraped = len(products_data)

        if products_data:
            inserted = insert_market_listings(products_data, dry_run=args.dry_run)
            total_inserted = inserted
        else:
            logger.warning("No products scraped", extra={"session_id": session_id})

    except FileNotFoundError as e:
        logger.error(str(e))
        print(f"\nError: {e}")
        print(f"\nCreate the URL file first:")
        print(f"  mkdir -p data")
        print(f"  echo 'https://paypayfleamarket.yahoo.co.jp/item/z546568632' > {url_file}")
        return

    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user", extra={"session_id": session_id})

    except Exception as e:
        logger.critical("Fatal error occurred", exc_info=True, extra={"session_id": session_id})

    finally:
        if not args.dry_run:
            close_db()

    # Final summary
    logger.info("=" * 60)
    logger.info("SCRAPER SESSION SUMMARY")
    logger.info("=" * 60)
    logger.info(
        "Session completed",
        extra={
            "session_id": session_id,
            "niche_type": args.niche,
            "dry_run": args.dry_run,
            "products_scraped": total_scraped,
            "products_inserted": total_inserted,
            "success_rate": f"{(total_inserted/total_scraped*100):.1f}%" if total_scraped > 0 else "N/A"
        }
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
