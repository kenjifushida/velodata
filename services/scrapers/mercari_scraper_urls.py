#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mercari Japan URL Scraper - Scrapes specific item URLs from a file.

This scraper reads Mercari Japan item URLs from a text file and scrapes
detailed product information from each page. Useful for targeted scraping
of specific items identified for potential arbitrage opportunities.

Architecture:
    - Strategy Pattern for niche-specific attribute extraction
    - Meta tag extraction (primary - reliable in SSR initial HTML)
    - DOM extraction with data-testid selectors (client-rendered content)
    - Condition rank mapping from Mercari's Japanese condition labels

Page Loading Strategy:
    Mercari uses Next.js with client-side rendering. Key differences from
    PayPay Flea Market:
    - Do NOT use wait_until='networkidle' - Mercari polls continuously,
      causing Playwright to wait indefinitely.
    - Use wait_until='domcontentloaded' + wait_for_selector for price element.
    - Meta tags in initial SSR HTML are reliable fallbacks for title, price,
      and og:image before JS completes rendering.

Condition Mapping (Mercari JP labels → Standard rank):
    新品、未使用     → N  (New, unused)
    未使用に近い     → S  (Nearly new)
    目立った傷や汚れなし → A  (No noticeable damage)
    やや傷や汚れあり   → B  (Some damage)
    傷や汚れあり     → C  (Damage present)
    全体的に状態が悪い  → D  (Poor overall condition)

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
    echo "https://jp.mercari.com/item/m30222262807" > data/mercari_urls.txt

    # Dry run - validate without database writes (uses data/mercari_urls.txt by default)
    python mercari_scraper_urls.py --niche TCG --dry-run --headed

    # Live run - save to market_listings collection
    python mercari_scraper_urls.py --niche TCG

    # Custom URL file (optional)
    python mercari_scraper_urls.py --niche WATCH --urls data/watch_urls.txt

Examples:
    # Scrape TCG cards (uses default file: data/mercari_urls.txt)
    python services/scrapers/mercari_scraper_urls.py --niche TCG --dry-run --headed

    # Scrape with translation enabled
    python services/scrapers/mercari_scraper_urls.py --niche TCG --translate --dry-run
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
from core.models.market_listing import create_mercari_listing, MarketListing
from core.logging import get_logger, log_execution_time
from core.tcg_games import (
    TCGGame,
    detect_tcg_game,
    extract_tcg_card_info,
    ALL_GAME_CONFIGS,
)
from core.llm import translate

# Initialize logger for this service
logger = get_logger("mercari-url-scraper")


# ============================================================================
# CONSTANTS
# ============================================================================

BASE_URL = "https://jp.mercari.com"

# Mercari item condition label → standard rank mapping
MERCARI_CONDITION_RANK_MAP: Dict[str, str] = {
    "新品、未使用": "N",
    "未使用に近い": "S",
    "目立った傷や汚れなし": "A",
    "やや傷や汚れあり": "B",
    "傷や汚れあり": "C",
    "全体的に状態が悪い": "D",
}

# Default URL file location (relative to project root)
DEFAULT_URL_FILE = PROJECT_ROOT / "data" / "mercari_urls.txt"

# Niche types supported
NicheType = Literal[
    "TCG", "WATCH", "CAMERA_GEAR", "LUXURY_ITEM",
    "VIDEOGAME", "STATIONARY", "COLLECTION_FIGURES"
]


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

    # Skip if title appears to already be in English (>80% ASCII)
    ascii_ratio = sum(1 for c in title if ord(c) < 128) / len(title) if title else 0
    if ascii_ratio > 0.8:
        logger.debug("Title appears to be English, skipping translation")
        return title

    try:
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
                "Translated title",
                extra={"original": title[:50], "translated": translated[:50]}
            )
            return translated.strip()
        return None

    except Exception as e:
        logger.warning(
            "Translation failed, continuing without translation",
            extra={"title": title[:50], "error": str(e)}
        )
        return None


# ============================================================================
# ATTRIBUTE EXTRACTORS (Strategy Pattern)
# ============================================================================

class AttributeExtractor(ABC):
    """
    Abstract base class for niche-specific attribute extraction.

    Each niche has unique fields that need to be extracted from the product
    title and description. This pattern allows for extensible extraction
    logic without modifying core scraping code.
    """

    @abstractmethod
    def extract(
        self,
        title: str,
        description: Optional[str],
        extra_data: Optional[Dict],
    ) -> Dict[str, Any]:
        """
        Extract niche-specific attributes from product data.

        Args:
            title: Product title
            description: Product description (may be None)
            extra_data: Additional structured data (may be None)

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
        extra_data: Optional[Dict],
    ) -> Dict[str, Any]:
        """Extract TCG card attributes using centralized detector."""
        card_info = extract_tcg_card_info(title)
        card_info["raw_title"] = title

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
        - case_size: Diameter in mm
        - movement: Automatic, Quartz, Manual
        - box_included: Original box present
        - papers_included: Original papers present
    """

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
        extra_data: Optional[Dict],
    ) -> Dict[str, Any]:
        """Extract watch attributes from product data."""
        attributes: Dict[str, Any] = {"raw_title": title}
        text = f"{title} {description or ''}"

        for brand in self.WATCH_BRANDS:
            if brand.lower() in text.lower():
                attributes["brand"] = brand.split("/")[0].strip()
                break

        ref_match = re.search(r'\b(\d{5,6}[A-Z]{0,3})\b', text)
        if ref_match:
            attributes["reference_number"] = ref_match.group(1)

        size_match = re.search(r'(\d{2,3})\s*mm', text, re.IGNORECASE)
        if size_match:
            attributes["case_size"] = f"{size_match.group(1)}mm"

        attributes["box_included"] = any(
            term in text for term in ["箱付", "箱あり", "BOX付", "with box", "付属品完備"]
        )
        attributes["papers_included"] = any(
            term in text for term in ["保証書", "ギャランティ", "papers", "warranty"]
        )

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
        - focal_length: For lenses (e.g., "24-70mm")
        - aperture: For lenses (e.g., "f/2.8")
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
        extra_data: Optional[Dict],
    ) -> Dict[str, Any]:
        """Extract camera gear attributes from product data."""
        attributes: Dict[str, Any] = {"raw_title": title}
        text = f"{title} {description or ''}"

        for brand in self.CAMERA_BRANDS:
            if brand.lower() in text.lower():
                attributes["brand"] = brand.split("/")[0].strip()
                break

        for subcat, patterns in self.SUBCATEGORY_PATTERNS.items():
            if any(p.lower() in text.lower() for p in patterns):
                attributes["subcategory"] = subcat
                break

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
        extra_data: Optional[Dict],
    ) -> Dict[str, Any]:
        """Extract luxury item attributes."""
        attributes: Dict[str, Any] = {"raw_title": title}
        text = f"{title} {description or ''}"

        for brand in self.LUXURY_BRANDS:
            if brand.lower() in text.lower():
                attributes["brand"] = brand.split("/")[0].strip()
                break

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
        extra_data: Optional[Dict],
    ) -> Dict[str, Any]:
        """Extract videogame attributes."""
        attributes: Dict[str, Any] = {"raw_title": title}
        text = f"{title} {description or ''}"

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
        extra_data: Optional[Dict],
    ) -> Dict[str, Any]:
        """Extract stationary attributes."""
        attributes: Dict[str, Any] = {"raw_title": title}
        text = f"{title} {description or ''}"

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
        extra_data: Optional[Dict],
    ) -> Dict[str, Any]:
        """Extract figure attributes."""
        attributes: Dict[str, Any] = {"raw_title": title}
        text = f"{title} {description or ''}"

        if any(term in text for term in ["フィギュア", "figure", "Figure"]):
            attributes["item_type"] = "FIGURE"
        elif any(term in text for term in ["プラモデル", "ガンプラ", "gundam", "model kit"]):
            attributes["item_type"] = "MODEL_KIT"
        elif any(term in text for term in ["ねんどろいど", "nendoroid"]):
            attributes["item_type"] = "NENDOROID"
        elif any(term in text for term in ["figma"]):
            attributes["item_type"] = "FIGMA"

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
        for _ in range(random.randint(2, 3)):
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            page.mouse.move(x, y)
            time.sleep(random.uniform(0.1, 0.2))

        # Scroll down to trigger lazy-loaded images
        page.evaluate("window.scrollBy(0, 400)")
        time.sleep(random.uniform(0.3, 0.5))

    except Exception as e:
        logger.warning(
            "Failed to simulate human behavior",
            extra={"correlation_id": correlation_id, "error": str(e)}
        )


# ============================================================================
# MERCARI-SPECIFIC DATA EXTRACTION
# ============================================================================

def extract_meta_tags(page: Page) -> Dict[str, str]:
    """
    Extract Open Graph and product meta tags from Mercari page.

    Mercari embeds reliable product data in meta tags as part of SSR
    initial HTML, making them available before client-side JS renders.
    Key tags used: og:title, og:description, og:image, product:price:amount.

    Args:
        page: Playwright page instance

    Returns:
        Dictionary of meta tag key → content value
    """
    try:
        return page.evaluate("""
            () => {
                const metas = {};
                const tags = document.querySelectorAll('meta[property], meta[name]');
                for (const tag of tags) {
                    const key = tag.getAttribute('property') || tag.getAttribute('name');
                    if (key) metas[key] = tag.getAttribute('content');
                }
                return metas;
            }
        """)
    except Exception:
        return {}


def extract_images_from_dom(page: Page) -> List[str]:
    """
    Extract product image URLs from Mercari's thumbnail carousel.

    Mercari uses a slick-slider carousel where each slide contains a
    [data-testid="imageThumbnail-{index}"] element with a picture > img.
    Targeting these elements precisely avoids picking up unrelated page
    images (seller avatar, related listings, etc.).

    Example DOM structure:
        .slick-track
          .slick-slide
            [data-testid="imageThumbnail-0"]
              picture > img[src="https://static.mercdn.net/.../m{id}_1.jpg?{ts}"]

    Args:
        page: Playwright page instance

    Returns:
        List of unique product image URLs ordered by carousel index
    """
    try:
        result = page.evaluate("""
            () => {
                const urls = [];
                const seen = new Set();

                // Primary: thumbnail carousel items (data-testid="imageThumbnail-{n}")
                const thumbnails = document.querySelectorAll('[data-testid^="imageThumbnail"] img');
                for (const img of thumbnails) {
                    const src = img.src || img.getAttribute('data-src');
                    if (src && !src.startsWith('data:') && src.includes('mercdn.net') && !seen.has(src)) {
                        // Strip cache-busting query param to get canonical URL
                        const cleanSrc = src.split('?')[0];
                        urls.push(cleanSrc);
                        seen.add(src);
                    }
                }

                // Fallback: slick-track imgs if data-testid pattern not found
                if (urls.length === 0) {
                    const slickImgs = document.querySelectorAll('.slick-track img');
                    for (const img of slickImgs) {
                        const src = img.src || img.getAttribute('data-src');
                        if (src && !src.startsWith('data:') && src.includes('mercdn.net') && !seen.has(src)) {
                            const cleanSrc = src.split('?')[0];
                            urls.push(cleanSrc);
                            seen.add(src);
                        }
                    }
                }

                return urls;
            }
        """)
        return result or []
    except Exception as e:
        logger.warning("DOM image extraction failed", extra={"error": str(e)})
        return []


def extract_condition_from_dom(page: Page) -> Optional[str]:
    """
    Extract item condition text from Mercari's item detail section.

    Tries multiple selector strategies to locate the condition label:
    1. data-testid="商品の状態" attribute
    2. dt/dd pairs where dt contains 商品の状態
    3. Direct text match against known condition labels

    Args:
        page: Playwright page instance

    Returns:
        Japanese condition text (e.g., "目立った傷や汚れなし") or None
    """
    try:
        return page.evaluate("""
            () => {
                // Strategy 1: data-testid with Japanese label
                const byTestId = document.querySelector('[data-testid="商品の状態"]');
                if (byTestId) return byTestId.textContent.trim();

                // Strategy 2: dt/dd pairs (item detail table pattern)
                const allDts = document.querySelectorAll('dt');
                for (const dt of allDts) {
                    if (dt.textContent.includes('商品の状態')) {
                        const dd = dt.nextElementSibling;
                        if (dd) return dd.textContent.trim();
                    }
                }

                // Strategy 3: Direct text content match on leaf elements
                const conditionLabels = [
                    '新品、未使用', '未使用に近い', '目立った傷や汚れなし',
                    'やや傷や汚れあり', '傷や汚れあり', '全体的に状態が悪い'
                ];
                const candidates = document.querySelectorAll('span, p');
                for (const elem of candidates) {
                    const text = elem.textContent.trim();
                    if (conditionLabels.includes(text)) {
                        return text;
                    }
                }

                return null;
            }
        """)
    except Exception:
        return None


def map_condition_to_rank(condition_text: Optional[str]) -> Optional[str]:
    """
    Map Mercari Japanese condition label to standard N/S/A/B/C/D rank.

    Args:
        condition_text: Japanese condition text from Mercari

    Returns:
        Rank string (N/S/A/B/C/D) or None if not mappable
    """
    if not condition_text:
        return None

    # Exact match first
    rank = MERCARI_CONDITION_RANK_MAP.get(condition_text.strip())
    if rank:
        return rank

    # Partial match as fallback (handles extra whitespace or truncation)
    for label, rank in MERCARI_CONDITION_RANK_MAP.items():
        if label in condition_text:
            return rank

    return None


def check_item_sold(page: Page) -> bool:
    """
    Check if a Mercari item has been sold.

    Checks for explicit sold indicators: sold-out badge element or
    presence of "売り切れ"/"SOLD" text. Does not rely on absence of
    checkout button to avoid false positives during slow renders.

    Args:
        page: Playwright page instance

    Returns:
        True if item is confirmed sold, False otherwise
    """
    try:
        return bool(page.evaluate("""
            () => {
                // Check for explicit sold-out badge
                const soldBadge = document.querySelector(
                    '[data-testid="sold-out-badge"], [class*="sold-out"], [class*="soldOut"]'
                );
                if (soldBadge) return true;

                // Check for SOLD overlay or aria label
                const soldOverlay = document.querySelector(
                    '[aria-label*="SOLD"], [aria-label*="売り切れ"]'
                );
                if (soldOverlay) return true;

                // Check page title for sold indicator
                const title = document.title || '';
                if (title.includes('売り切れ') || title.includes('SOLD')) return true;

                return false;
            }
        """))
    except Exception:
        return False


# ============================================================================
# PRODUCT DATA EXTRACTION
# ============================================================================

def extract_product_data(
    page: Page,
    url: str,
    niche_type: NicheType,
    correlation_id: str,
    enable_translation: bool = False
) -> Optional[Dict]:
    """
    Extract product data from a Mercari item page.

    Loading strategy:
        1. Navigate with wait_until='domcontentloaded' (NOT networkidle)
        2. Wait for [data-testid="price"] to confirm JS render is complete
        3. Simulate human behavior (triggers lazy image loading via scroll)
        4. Extract meta tags (SSR-reliable: title, price, og:image)
        5. Extract DOM elements (condition, description, gallery images)
        6. Fall back to meta tags for any missing fields

    Args:
        page: Playwright page instance
        url: Mercari item URL to scrape
        niche_type: Product niche type for attribute extraction
        correlation_id: Session correlation ID
        enable_translation: Whether to translate titles to English

    Returns:
        Dictionary with product data or None if extraction fails
    """
    try:
        # Extract item ID from URL (Mercari format: m{digits})
        id_match = re.search(r'/item/(m\w+)', url)
        if not id_match:
            logger.warning(
                "Could not extract item ID from URL",
                extra={"url": url, "correlation_id": correlation_id}
            )
            return None

        external_id = id_match.group(1)

        # Navigate - domcontentloaded avoids networkidle timeout on Mercari
        response = page.goto(url, wait_until='domcontentloaded', timeout=30000)

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

        # Wait for price element - confirms client-side rendering is complete
        try:
            page.wait_for_selector('[data-testid="price"]', timeout=15000)
        except Exception:
            logger.warning(
                "Price element not found after 15s - item may be sold or unavailable",
                extra={"url": url, "correlation_id": correlation_id}
            )
            # Continue - attempt extraction anyway using meta tag fallbacks

        # Human simulation - also triggers lazy image loading via scroll
        time.sleep(random.uniform(1.0, 2.0))
        simulate_human_behavior(page, correlation_id)

        # === SOLD STATUS CHECK ===
        if check_item_sold(page):
            logger.info(
                "Item is sold, skipping",
                extra={"external_id": external_id, "correlation_id": correlation_id}
            )
            return None

        # === META TAGS (SSR - available in initial HTML before JS) ===
        meta_tags = extract_meta_tags(page)

        title: Optional[str] = None
        description: Optional[str] = None
        price_jpy: Optional[int] = None
        image_urls: List[str] = []

        # === PRIMARY: DOM Extraction (client-rendered content) ===
        try:
            name_elem = page.locator('[data-testid="name"]').first
            if name_elem.count() > 0:
                title = name_elem.inner_text(timeout=3000).strip()
        except Exception:
            pass

        try:
            price_elem = page.locator('[data-testid="price"]').first
            if price_elem.count() > 0:
                price_text = price_elem.inner_text(timeout=3000)
                price_clean = re.sub(r'[^\d]', '', price_text)
                if price_clean:
                    price_jpy = int(price_clean)
        except Exception:
            pass

        try:
            desc_elem = page.locator('[data-testid="description"]').first
            if desc_elem.count() > 0:
                description = desc_elem.inner_text(timeout=3000).strip()
        except Exception:
            pass

        # === FALLBACK: Meta Tags ===
        if not title:
            og_title = meta_tags.get("og:title", "")
            # Strip site name suffix: "商品名 | メルカリ" → "商品名"
            title = re.split(r'\s*[\|｜]\s*', og_title)[0].strip() if og_title else None

        if not description:
            description = meta_tags.get("og:description") or meta_tags.get("description")

        if not price_jpy:
            price_meta = meta_tags.get("product:price:amount")
            if price_meta:
                try:
                    price_jpy = int(float(price_meta))
                except (ValueError, TypeError):
                    pass

        # === IMAGE EXTRACTION ===
        og_image = meta_tags.get("og:image")

        # Primary: DOM gallery images (loaded after scroll simulation)
        dom_images = extract_images_from_dom(page)
        if dom_images:
            image_urls = dom_images
            logger.debug(
                f"Extracted {len(image_urls)} gallery images from DOM",
                extra={"external_id": external_id, "correlation_id": correlation_id}
            )
        elif og_image:
            # Fallback: og:image (reliable from SSR meta tags)
            image_urls = [og_image]
            logger.debug(
                "Using og:image as fallback",
                extra={"external_id": external_id, "correlation_id": correlation_id}
            )

        # === CONDITION EXTRACTION ===
        condition_text = extract_condition_from_dom(page)
        condition_rank = map_condition_to_rank(condition_text)

        if condition_text:
            logger.debug(
                "Extracted condition",
                extra={
                    "condition": condition_text,
                    "rank": condition_rank,
                    "external_id": external_id
                }
            )

        # === VALIDATION ===
        if not title:
            logger.warning(
                "Could not extract title, using placeholder",
                extra={"url": url, "correlation_id": correlation_id}
            )
            title = f"Mercari Item {external_id}"

        if not price_jpy:
            logger.warning(
                "Could not extract price - skipping item",
                extra={"url": url, "correlation_id": correlation_id}
            )
            return None  # Price is required for arbitrage analysis

        # === NICHE-SPECIFIC ATTRIBUTE EXTRACTION ===
        extractor = ATTRIBUTE_EXTRACTORS.get(niche_type)
        if extractor:
            attributes = extractor.extract(title, description, None)
        else:
            attributes = {"raw_title": title}
            if description:
                attributes["raw_description"] = description[:1000]

        # Add condition info to attributes
        if condition_text:
            attributes["condition_label"] = condition_text
        if condition_rank:
            attributes["condition_rank"] = condition_rank

        # === TRANSLATION ===
        if enable_translation:
            title_en = translate_title_safe(title, niche_type, enable_translation)
            if title_en:
                attributes["title_en"] = title_en

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
    Load Mercari Japan item URLs from a text file.

    File format:
        - One URL per line
        - Lines starting with # are comments
        - Empty lines are ignored
        - URLs must match: https://jp.mercari.com/item/m{id}

    Args:
        file_path: Path to the URL file

    Returns:
        List of valid Mercari item URLs

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

            # Validate Mercari URL format
            if not re.match(r'https://jp\.mercari\.com/item/m\w+', line):
                logger.warning(
                    f"Invalid Mercari URL format on line {line_num}, skipping: {line[:50]}"
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
    session_id: Optional[str] = None,
    enable_translation: bool = False
) -> List[Dict]:
    """
    Scrape product data from a list of Mercari item URLs.

    Reuses a single browser page across all URLs to minimize browser
    overhead. Rate limiting between requests reduces risk of detection.

    Args:
        urls: List of Mercari item URLs to scrape
        niche_type: Product niche type
        headless: Whether to run browser in headless mode
        session_id: Scraping session correlation ID
        enable_translation: Whether to translate titles to English

    Returns:
        List of scraped product dictionaries (failed extractions omitted)
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
                        page, url, niche_type, correlation_id, enable_translation
                    )

                    if product_data:
                        products.append(product_data)
                        logger.info(
                            f"Successfully extracted: {product_data['external_id']} "
                            f"({product_data['title'][:40]}...)",
                            extra={
                                "external_id": product_data["external_id"],
                                "price_jpy": product_data["price_jpy"],
                                "correlation_id": correlation_id
                            }
                        )
                    else:
                        logger.warning(
                            "Failed to extract data from URL",
                            extra={"url": url, "correlation_id": correlation_id}
                        )

                except Exception:
                    logger.error(
                        "Error scraping URL",
                        exc_info=True,
                        extra={"url": url, "correlation_id": correlation_id}
                    )

                # Rate limiting between requests
                if idx < len(urls):
                    delay = random.uniform(2, 4)
                    logger.debug(
                        f"Rate limiting: waiting {delay:.1f}s before next request",
                        extra={"correlation_id": correlation_id}
                    )
                    time.sleep(delay)

        finally:
            browser.close()

    logger.info(
        "URL scrape session complete",
        extra={
            "total_urls": len(urls),
            "successful": len(products),
            "failed": len(urls) - len(products),
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

    Uses upsert by _id and URL to avoid duplicate entries when the same
    item is scraped multiple times.

    Args:
        products_data: List of scraped product dictionaries
        dry_run: If True, validate and print results without database writes

    Returns:
        Number of products successfully processed
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
            listing = create_mercari_listing(
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
                attrs = listing.attributes

                print(f"\n{'='*70}")
                print(f"Listing ID:  {listing.id}")
                print(f"Niche Type:  {listing.niche_type}")

                # TCG-specific display
                if listing.niche_type == "TCG" and attrs.get("game"):
                    game = attrs.get("game")
                    try:
                        tcg_game = TCGGame(game)
                        config = ALL_GAME_CONFIGS.get(tcg_game)
                        game_display = config.display_name_en if config else game
                    except ValueError:
                        game_display = game
                    print(f"TCG Game:    {game_display}")
                    if attrs.get("is_graded"):
                        print(f"Graded:      Yes ({attrs.get('grading_company')} {attrs.get('grade')})")
                    if attrs.get("set_code"):
                        print(f"Set Code:    {attrs.get('set_code')}")
                    if attrs.get("rarity"):
                        print(f"Rarity:      {attrs.get('rarity')}")

                # Brand info for non-TCG niches
                if attrs.get("brand"):
                    print(f"Brand:       {attrs['brand']}")

                # Condition
                if attrs.get("condition_label"):
                    rank = attrs.get("condition_rank", "N/A")
                    print(f"Condition:   {attrs['condition_label']} (Rank: {rank})")

                print(f"Title (JP):  {listing.title[:60]}")
                if attrs.get("title_en"):
                    print(f"Title (EN):  {attrs['title_en'][:60]}")
                print(f"Price:       ¥{listing.price_jpy:,}")
                print(f"URL:         {listing.url}")
                if listing.image_urls:
                    print(f"Images:      {len(listing.image_urls)} image(s)")
                    print(f"  First:     {str(listing.image_urls[0])[:80]}")
                print(f"{'='*70}")
                inserted_count += 1

            else:
                # Check for existing listing to avoid duplicates
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
        except Exception:
            error_count += 1
            logger.error(
                "Error processing listing",
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
    """Main entry point for the Mercari URL scraper."""
    parser = argparse.ArgumentParser(
        description="Mercari Japan URL Scraper - Scrapes specific item URLs from a file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run with default URL file (data/mercari_urls.txt)
  python mercari_scraper_urls.py --niche TCG --dry-run --headed

  # Custom URL file (optional)
  python mercari_scraper_urls.py --niche WATCH --urls data/watch_urls.txt --dry-run

  # Live run - save to database
  python mercari_scraper_urls.py --niche TCG

  # With Japanese to English translation
  python mercari_scraper_urls.py --niche TCG --translate --dry-run

URL File Format (data/mercari_urls.txt):
  # Comments start with #
  https://jp.mercari.com/item/m30222262807
  https://jp.mercari.com/item/m12345678901
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
        help="Path to URL file (optional, default: data/mercari_urls.txt)"
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

    args = parser.parse_args()

    # Determine URL file path
    url_file = Path(args.urls) if args.urls else DEFAULT_URL_FILE

    # Session setup
    session_id = str(uuid.uuid4())[:8]
    logger.info("=" * 60)
    logger.info("VELODATA - MERCARI URL SCRAPER")
    logger.info("=" * 60)
    logger.info(
        "Starting scraper session",
        extra={
            "session_id": session_id,
            "niche_type": args.niche,
            "url_file": str(url_file),
            "headless": not args.headed,
            "dry_run": args.dry_run,
            "translate": args.translate,
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
            f"Loaded {len(urls)} URL(s) from file",
            extra={"file": str(url_file), "session_id": session_id}
        )

        # Scrape all URLs
        products_data = scrape_urls(
            urls=urls,
            niche_type=args.niche,
            headless=not args.headed,
            session_id=session_id,
            enable_translation=args.translate
        )

        total_scraped = len(products_data)

        if products_data:
            inserted = insert_market_listings(products_data, dry_run=args.dry_run)
            total_inserted = inserted
        else:
            logger.warning("No products scraped successfully", extra={"session_id": session_id})

    except FileNotFoundError as e:
        logger.error(str(e))
        print(f"\nError: {e}")
        print(f"\nCreate the URL file first:")
        print(f"  mkdir -p data")
        print(f"  echo 'https://jp.mercari.com/item/m30222262807' > {url_file}")
        return

    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user", extra={"session_id": session_id})

    except Exception:
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
            "success_rate": f"{(total_inserted / total_scraped * 100):.1f}%" if total_scraped > 0 else "N/A"
        }
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
