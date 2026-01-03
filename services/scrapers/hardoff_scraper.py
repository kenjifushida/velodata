#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hard-Off Scraper - Scrapes netmall.hardoff.co.jp and saves to market_listings collection.

Scrapes product listings from Hard-Off (Japanese secondhand marketplace) and stores them
in the market_listings MongoDB collection for later processing by the matching pipeline.

The scraper is completely independent from the seeder service - it only extracts available
information from Hard-Off pages and creates market listing documents.

Supported Categories:
    - watches: Luxury and vintage wristwatches
    - camera_gear: Digital cameras, lenses, and photography equipment
    - luxury_items: Designer bags, wallets, and accessories (includes subcategories)
    - videogames: Game consoles (standing, portable, hybrid)
    - stationary: Writing utensils, fountain pens, and office supplies (includes subcategories)

Usage:
    # Dry run (don't save to database, just print)
    python hardoff_scraper.py --category watches --max-pages 2 --dry-run

    # Live run (save to market_listings collection)
    python hardoff_scraper.py --category watches --max-pages 5
    python hardoff_scraper.py --category camera_gear --max-pages 10
    python hardoff_scraper.py --category luxury_items --max-pages 5
    python hardoff_scraper.py --category stationary --max-pages 5

    # Filter by condition ranks (only scrape items in specific conditions)
    python hardoff_scraper.py --category watches --max-pages 5 --ranks N S A
    python hardoff_scraper.py --category luxury_items --max-pages 10 --ranks N S

    # Search by keyword (must specify niche type and keyword)
    # Keyword search automatically filters by category to only show results from that niche
    python hardoff_scraper.py --niche VIDEOGAME --keyword "ゲームボーイ" --max-pages 5
    python hardoff_scraper.py --niche LUXURY_ITEM --keyword "LOUIS VUITTON" --max-pages 10 --ranks N S A
    python hardoff_scraper.py --niche STATIONARY --keyword "万年筆" --max-pages 5
    python hardoff_scraper.py --niche STATIONARY --keyword "Montblanc" --max-pages 3

    # Available ranks: N (New), S (Nearly New), A (Excellent), B (Good),
    #                  C (Fair), D (Poor), JUNK (For parts/not working)
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
import urllib.parse
from typing import List, Dict, Optional, Literal
from datetime import datetime
from bs4 import BeautifulSoup
from pydantic import BaseModel, ValidationError

try:
    from curl_cffi import requests
except ImportError:
    print("curl_cffi not installed. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "curl-cffi>=0.5.0"])
    from curl_cffi import requests

from core.database import get_db, close_db
from core.models.market_listing import (
    create_hardoff_listing,
    MarketListing,
    normalize_condition_rank,
    ConditionRank
)
from core.logging import get_logger, log_execution_time

# Initialize logger for this service
logger = get_logger("hardoff-scraper")


# ============================================================================
# HARD-OFF CONSTANTS
# ============================================================================

BASE_URL = "https://netmall.hardoff.co.jp"

# ============================================================================
# CATEGORY CONFIGURATION
# ============================================================================

class CategoryConfig(BaseModel):
    """
    Configuration for a scrapeable Hard-Off category.

    Attributes:
        url: Base URL for the category page
        niche_type: Product niche classification
        display_name: Human-readable category name
        subcategories: Optional list of subcategory URLs to scrape
    """
    url: str
    niche_type: Literal["WATCH", "CAMERA_GEAR", "LUXURY_ITEM", "POKEMON_CARD", "VIDEOGAME", "STATIONARY"]
    display_name: str
    subcategories: Optional[List[str]] = None


# Category registry - maps CLI argument names to category configurations
CATEGORIES: Dict[str, CategoryConfig] = {
    "watches": CategoryConfig(
        url="https://netmall.hardoff.co.jp/cate/000100040001/",
        niche_type="WATCH",
        display_name="Watches",
    ),
    "camera_gear": CategoryConfig(
        url="https://netmall.hardoff.co.jp/cate/00010003/",
        niche_type="CAMERA_GEAR",
        display_name="Camera Gear",
    ),
    "luxury_items": CategoryConfig(
        url="https://netmall.hardoff.co.jp/cate/00010013/",
        niche_type="LUXURY_ITEM",
        display_name="Luxury Items",
        subcategories=[
            "https://netmall.hardoff.co.jp/cate/000100130001/",  # Luxury Bags
            "https://netmall.hardoff.co.jp/cate/000100130002/",  # Luxury Wallets
        ],
    ),
    "videogames": CategoryConfig(
        url="https://netmall.hardoff.co.jp/cate/00010012/",
        niche_type="VIDEOGAME",
        display_name="Videogames",
        subcategories=[
            "https://netmall.hardoff.co.jp/cate/0001001200010001/",  # Standing Game Consoles
            "https://netmall.hardoff.co.jp/cate/0001001200010002/",  # Portable Game Consoles
            "https://netmall.hardoff.co.jp/cate/0001001200010003/",  # Hybrid Game Consoles
        ],
    ),
    "stationary": CategoryConfig(
        url="https://netmall.hardoff.co.jp/cate/000100070008/",
        niche_type="STATIONARY",
        display_name="Stationary",
        subcategories=[
            "https://netmall.hardoff.co.jp/cate/0001000700080001/",  # Writing Utensils
            "https://netmall.hardoff.co.jp/cate/00010007000800010001/",  # Fountain Pens
        ],
    ),
}

# Niche type to category ID mapping for keyword searches
# Maps niche types to Hard-Off category IDs to filter search results
NICHE_CATEGORY_IDS: Dict[str, str] = {
    "WATCH": "000100040001",
    "CAMERA_GEAR": "00010003",
    "LUXURY_ITEM": "00010013",
    "POKEMON_CARD": "00010002",  # Trading Cards category
    "VIDEOGAME": "00010012",
    "STATIONARY": "000100070008",
}

# Rank filter mapping (Hard-Off query parameters)
# rank=1 -> N (New), rank=2 -> S (Nearly New), rank=3 -> A (Excellent)
# rank=4 -> B (Good), rank=5 -> C (Fair), rank=6 -> D (Poor)
RANK_QUERY_MAP = {
    "N": "1",
    "S": "2",
    "A": "3",
    "B": "4",
    "C": "5",
    "D": "6",
    "JUNK": "7",
}


# ============================================================================
# SCRAPING FUNCTIONS
# ============================================================================

@log_execution_time(logger)
def scrape_hardoff_category(
    category_url: str,
    niche_type: str,
    max_pages: int = 5,
    ranks: Optional[List[str]] = None,
    keyword: Optional[str] = None,
    session_id: Optional[str] = None
) -> List[Dict]:
    """
    Scrape Hard-Off category pages or keyword search results for product listings.

    Args:
        category_url: Hard-Off category URL (not used for keyword searches)
        niche_type: Product niche type (CAMERA_GEAR, WATCH, LUXURY_ITEM, VIDEOGAME, STATIONARY)
        max_pages: Maximum number of pages to scrape
        ranks: Optional list of condition ranks to filter (e.g., ['N', 'S', 'A'])
        keyword: Optional search keyword (e.g., "ゲームボーイ", "LOUIS VUITTON", "Montblanc")
                 When provided, search is automatically filtered by niche category
        session_id: Scraping session correlation ID

    Returns:
        List of scraped product dictionaries

    Note:
        Keyword searches use Hard-Off's search API with category filtering to ensure
        results only come from the specified niche type. This prevents irrelevant
        results from other categories.
    """
    correlation_id = session_id or str(uuid.uuid4())[:8]
    logger.info(
        f"Starting Hard-Off scrape",
        extra={
            "category_url": category_url,
            "niche_type": niche_type,
            "max_pages": max_pages,
            "ranks": ranks,
            "keyword": keyword,
            "correlation_id": correlation_id
        }
    )

    products = []
    page = 1

    # Create session with browser-like headers
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    while page <= max_pages:
        try:
            # Build query parameters
            params = []

            # Keyword search mode
            if keyword:
                # For keyword searches, use search endpoint with 'q' parameter and category filter
                # URL format: https://netmall.hardoff.co.jp/search/?q={keyword}&cate={category_id}&s=7
                params.append(f"q={urllib.parse.quote(keyword)}")

                # Add category filter to restrict search to specific niche
                if niche_type in NICHE_CATEGORY_IDS:
                    category_id = NICHE_CATEGORY_IDS[niche_type]
                    params.append(f"cate={category_id}")
                    logger.debug(
                        f"Filtering keyword search by category",
                        extra={"niche_type": niche_type, "category_id": category_id}
                    )

                params.append("s=7")  # Sort parameter (7 = newest)

                # Add rank filters if specified
                if ranks:
                    for rank in ranks:
                        if rank in RANK_QUERY_MAP:
                            params.append(f"rank={RANK_QUERY_MAP[rank]}")

                # Add page parameter
                if page > 1:
                    params.append(f"page={page}")

                # Use search endpoint
                url = f"{BASE_URL}/search/?{'&'.join(params)}"
            else:
                # Category browsing mode (original logic)
                # Add rank filters if specified
                if ranks:
                    params.append("s=1")  # Enable search/filter mode
                    for rank in ranks:
                        if rank in RANK_QUERY_MAP:
                            params.append(f"rank={RANK_QUERY_MAP[rank]}")

                # Add page parameter
                if page > 1:
                    params.append(f"page={page}")

                # Construct URL with parameters
                if params:
                    url = f"{category_url}?{'&'.join(params)}"
                else:
                    url = category_url

            logger.debug(
                f"Fetching page {page}",
                extra={"url": url, "correlation_id": correlation_id}
            )

            # Fetch page with curl_cffi (bypasses some bot detection)
            response = session.get(url, headers=headers, timeout=30, impersonate="chrome110")

            if response.status_code != 200:
                logger.error(
                    f"Failed to fetch page {page}",
                    extra={
                        "status_code": response.status_code,
                        "correlation_id": correlation_id
                    }
                )
                break

            # Parse HTML
            soup = BeautifulSoup(response.text, 'lxml')

            # Find product cards
            product_cards = soup.select('.itemcolmn_item')

            if not product_cards:
                logger.info(
                    f"No products found on page {page}, stopping",
                    extra={"correlation_id": correlation_id}
                )
                break

            logger.info(
                f"Found {len(product_cards)} products on page {page}",
                extra={"count": len(product_cards), "correlation_id": correlation_id}
            )

            # Extract product data
            for idx, card in enumerate(product_cards):
                try:
                    product_data = extract_product_from_card(card, niche_type, correlation_id, session)
                    if product_data:
                        # Client-side rank filtering (Hard-Off server filtering may be unreliable)
                        if ranks:
                            product_rank = product_data.get('attributes', {}).get('condition_rank')
                            if product_rank and product_rank not in ranks:
                                logger.debug(
                                    f"Skipping product {product_data.get('external_id')} - rank {product_rank} not in filter {ranks}",
                                    extra={"correlation_id": correlation_id}
                                )
                                continue

                        products.append(product_data)
                        logger.debug(
                            f"Extracted product: {product_data.get('external_id')}",
                            extra={"correlation_id": correlation_id}
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to extract product {idx + 1} on page {page}",
                        exc_info=True,
                        extra={"correlation_id": correlation_id}
                    )
                    continue

            # Rate limiting - be respectful
            time.sleep(2)
            page += 1

        except Exception as e:
            logger.error(
                f"Error scraping page {page}",
                exc_info=True,
                extra={"correlation_id": correlation_id}
            )
            break

    logger.info(
        f"Scraping complete. Extracted {len(products)} products",
        extra={"total_products": len(products), "correlation_id": correlation_id}
    )

    return products


def upgrade_image_resolution(image_url: str) -> str:
    """
    Upgrade Hard-Off ImageFlux URL to high resolution (1280x1280).

    Hard-Off uses ImageFlux CDN with query parameters like w=231,h=182.
    This function replaces those with w=1280,h=1280 for eBay export quality.

    Args:
        image_url: Original image URL from Hard-Off

    Returns:
        Image URL with upgraded resolution parameters
    """
    # ImageFlux URLs have format: https://p1-d9ebd2ee.imageflux.jp/c!/w=231,h=182,a=0,u=0,q=75/103061/image.jpg
    # We want to replace w=XXX,h=YYY with w=1280,h=1280
    if 'imageflux.jp' in image_url and '/c!/' in image_url:
        # Replace width parameter
        image_url = re.sub(r'w=\d+', 'w=1280', image_url)
        # Replace height parameter
        image_url = re.sub(r'h=\d+', 'h=1280', image_url)

    return image_url


def fetch_product_images(product_url: str, session: requests.Session, correlation_id: str) -> List[str]:
    """
    Fetch all product images from the product detail page.

    Args:
        product_url: URL to the product detail page
        session: curl_cffi session for making requests
        correlation_id: Session correlation ID for logging

    Returns:
        List of high-resolution image URLs extracted from the product detail page
    """
    try:
        logger.debug(
            f"Fetching product images from detail page",
            extra={"url": product_url, "correlation_id": correlation_id}
        )

        # Fetch the product detail page using the existing session
        response = session.get(product_url, timeout=30, impersonate="chrome110")

        if response.status_code != 200:
            logger.warning(
                f"Failed to fetch product detail page: {response.status_code}",
                extra={"url": product_url, "correlation_id": correlation_id}
            )
            return []

        # Parse HTML
        soup = BeautifulSoup(response.text, 'lxml')

        # Small delay to be respectful to the server
        time.sleep(0.5)

        # Find the product images wrapper
        images_wrapper = soup.select_one('.product-detail-images-wrapper ul')
        if not images_wrapper:
            logger.warning(
                "Could not find product-detail-images-wrapper",
                extra={"url": product_url, "correlation_id": correlation_id}
            )
            return []

        # Extract all image URLs from the wrapper
        image_urls = []
        for img_elem in images_wrapper.select('li img'):
            img_src = img_elem.get('src', '')
            # Skip placeholder images
            if img_src and not img_src.startswith('data:') and 'blankimg' not in img_src:
                # Make absolute URL if needed
                if img_src.startswith('http'):
                    full_url = img_src
                else:
                    full_url = BASE_URL + img_src

                # Upgrade to high resolution for eBay export quality
                high_res_url = upgrade_image_resolution(full_url)
                image_urls.append(high_res_url)

        logger.debug(
            f"Extracted {len(image_urls)} high-resolution images from product detail page",
            extra={"url": product_url, "correlation_id": correlation_id, "count": len(image_urls)}
        )

        return image_urls

    except Exception as e:
        logger.error(
            "Failed to fetch product images",
            exc_info=True,
            extra={"url": product_url, "correlation_id": correlation_id}
        )
        return []


def extract_product_from_card(
    card: BeautifulSoup,
    niche_type: str,
    correlation_id: str,
    session: requests.Session
) -> Optional[Dict]:
    """
    Extract product data from a Hard-Off product card HTML element.

    Args:
        card: BeautifulSoup element for product card
        niche_type: Product niche type
        correlation_id: Session correlation ID
        session: curl_cffi session for fetching product details

    Returns:
        Dictionary with product data or None if extraction fails
    """
    try:
        # Extract product URL and ID
        link_elem = card.select_one('a[href*="/product/"]')
        if not link_elem:
            return None

        product_url = link_elem.get('href', '')
        if not product_url.startswith('http'):
            product_url = BASE_URL + product_url

        # Extract product ID from URL (e.g., /product/5705008/ -> 5705008)
        product_id_match = re.search(r'/product/(\d+)/', product_url)
        if not product_id_match:
            return None
        external_id = product_id_match.group(1)

        # Extract elements
        brand_elem = card.select_one('.item-brand-name')
        name_elem = card.select_one('.item-name')
        code_elem = card.select_one('.item-code')

        brand = brand_elem.get_text(strip=True) if brand_elem else None
        name = name_elem.get_text(strip=True) if name_elem else None
        code = code_elem.get_text(strip=True) if code_elem else None

        # Build full title for display
        parts = []
        if brand:
            parts.append(brand)
        if name:
            parts.append(name)
        if code:
            parts.append(code)

        title = " ".join(parts) if parts else "Unknown Product"

        # Extract price
        price_elem = card.select_one('.item-price-en')
        if not price_elem:
            return None

        price_text = price_elem.get_text(strip=True).replace(',', '').replace('円', '')
        try:
            price_jpy = int(price_text)
        except ValueError:
            logger.warning(
                f"Could not parse price: {price_text}",
                extra={"external_id": external_id, "correlation_id": correlation_id}
            )
            return None

        # Extract condition rank
        rank_elem = card.select_one('img[alt][src*="rank"]')
        condition_rank = None
        if rank_elem:
            rank_alt = rank_elem.get('alt', '').upper()
            try:
                condition_rank = normalize_condition_rank(rank_alt)
            except ValueError:
                logger.debug(
                    f"Could not normalize rank: {rank_alt}",
                    extra={"external_id": external_id, "correlation_id": correlation_id}
                )

        # Fetch all images from product detail page
        image_urls = fetch_product_images(product_url, session, correlation_id)

        # Build attributes dictionary with common fields
        attributes = {
            "condition_rank": condition_rank,
            "raw_title": title,  # Keep original title for NLP processing
        }

        # Extract niche-specific fields using Strategy pattern
        extractor = FIELD_EXTRACTORS.get(niche_type)
        if extractor:
            niche_attributes = extractor.extract_attributes(brand, name, code)
            attributes.update(niche_attributes)
        else:
            logger.warning(
                f"No field extractor found for niche type: {niche_type}",
                extra={"external_id": external_id, "correlation_id": correlation_id}
            )

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
            "Failed to extract product from card",
            exc_info=True,
            extra={"correlation_id": correlation_id}
        )
        return None


# ============================================================================
# FIELD EXTRACTORS (Strategy Pattern)
# ============================================================================

class FieldExtractor:
    """Base class for niche-specific field extraction strategies."""

    def extract_attributes(
        self,
        brand: str | None,
        name: str | None,
        code: str | None
    ) -> Dict:
        """
        Extract niche-specific attributes from parsed HTML fields.

        Args:
            brand: Brand from .item-brand-name
            name: Name/description from .item-name
            code: Model/reference code from .item-code

        Returns:
            Dictionary with extracted attributes
        """
        raise NotImplementedError


class CameraGearExtractor(FieldExtractor):
    """
    Field extractor for Camera Gear products.

    Hard-Off HTML structure for camera gear:
    - .item-brand-name: Brand (e.g., "NIKON", "CANON", "SONY")
    - .item-name: Subcategory (e.g., "デジタルカメラ", "レンズ", "ビデオカメラ")
    - .item-code: Model number (e.g., "D90", "EOS R5", "RF 24-70mm")
    """

    # Japanese subcategory to English mapping
    SUBCATEGORY_MAP = {
        "デジタルカメラ": "CAMERA",
        "デジタル一眼": "CAMERA",
        "一眼レフ": "CAMERA",
        "ミラーレス": "CAMERA",
        "コンパクトカメラ": "CAMERA",
        "レンズ": "LENS",
        "交換レンズ": "LENS",
        "ビデオカメラ": "VIDEO_CAMERA",
        "三脚": "PHOTO_ACCESSORY",
        "ストロボ": "PHOTO_ACCESSORY",
        "フラッシュ": "PHOTO_ACCESSORY",
        "カメラバッグ": "PHOTO_ACCESSORY",
        "フィルムカメラ": "CAMERA",
        "防犯カメラ": "VIDEO_CAMERA",
        "ペットカメラ": "VIDEO_CAMERA",
    }

    def extract_attributes(
        self,
        brand: str | None,
        name: str | None,
        code: str | None
    ) -> Dict:
        attributes = {}

        if brand:
            attributes["brand"] = brand

        if name:
            # Try to map Japanese subcategory to English enum
            for jp_term, eng_category in self.SUBCATEGORY_MAP.items():
                if jp_term in name:
                    attributes["subcategory"] = eng_category
                    break

            # Store raw subcategory name for debugging/future NLP
            attributes["subcategory_raw"] = name

        if code:
            attributes["model_number"] = code

        return attributes


class WatchExtractor(FieldExtractor):
    """
    Field extractor for Watch products.

    Hard-Off HTML structure for watches:
    - .item-brand-name: Brand (e.g., "SEIKO", "CASIO", "ROLEX")
    - .item-name: Model name (e.g., "自動巻き腕時計", "クォーツ腕時計", "G-SHOCK")
    - .item-code: Reference number (e.g., "4R36-04Y0", "DW-6900")
    """

    def extract_attributes(
        self,
        brand: str | None,
        name: str | None,
        code: str | None
    ) -> Dict:
        attributes = {}

        if brand:
            attributes["brand"] = brand

        if name:
            # Store model name from .item-name
            attributes["model"] = name

        if code:
            # Reference number from .item-code
            attributes["reference_number"] = code

        return attributes


class LuxuryItemExtractor(FieldExtractor):
    """
    Field extractor for Luxury Item products (bags, wallets, accessories).

    Hard-Off HTML structure for luxury items:
    - .item-brand-name: Brand (e.g., "LOUIS VUITTON", "CHANEL", "GUCCI", "HERMÈS")
    - .item-name: Product name/description (e.g., "ハンドバッグ", "長財布", "スカーフ")
    - .item-code: Model/reference number (e.g., "M51365", "A80603")
    """

    # Japanese subcategory to English mapping
    SUBCATEGORY_MAP = {
        # Bags
        "バッグ": "BAG",
        "ハンドバッグ": "BAG",
        "ショルダーバッグ": "BAG",
        "トートバッグ": "BAG",
        "クラッチバッグ": "BAG",
        "リュック": "BAG",
        "バックパック": "BAG",
        "ボストンバッグ": "BAG",
        "ウエストバッグ": "BAG",
        # Wallets
        "財布": "WALLET",
        "長財布": "WALLET",
        "二つ折り財布": "WALLET",
        "三つ折り財布": "WALLET",
        "コインケース": "WALLET",
        "カードケース": "WALLET",
        "キーケース": "WALLET",
        # Accessories
        "スカーフ": "ACCESSORY",
        "ベルト": "ACCESSORY",
        "サングラス": "ACCESSORY",
        "時計": "ACCESSORY",
        "ジュエリー": "ACCESSORY",
        "アクセサリー": "ACCESSORY",
    }

    def extract_attributes(
        self,
        brand: str | None,
        name: str | None,
        code: str | None
    ) -> Dict:
        attributes = {}

        if brand:
            attributes["brand"] = brand

        if name:
            # Try to map Japanese subcategory to English enum
            for jp_term, eng_category in self.SUBCATEGORY_MAP.items():
                if jp_term in name:
                    attributes["subcategory"] = eng_category
                    break

            # Store raw subcategory name for debugging/future NLP
            attributes["subcategory_raw"] = name

        if code:
            # Model/reference number from .item-code
            attributes["model_number"] = code

        return attributes


class VideogameExtractor(FieldExtractor):
    """
    Field extractor for Videogame products (game consoles).

    Hard-Off HTML structure for videogames:
    - .item-brand-name: Brand/Manufacturer (e.g., "Nintendo", "Sony", "Microsoft")
    - .item-name: Console type/description (e.g., "据置型ゲーム機", "携帯型ゲーム機")
    - .item-code: Model number (e.g., "Switch", "PlayStation 5", "Xbox Series X")
    """

    # Japanese subcategory to English mapping
    SUBCATEGORY_MAP = {
        # Standing/Home Consoles (据置型)
        "据置型": "STANDING_CONSOLE",
        "据置型ゲーム機": "STANDING_CONSOLE",
        "据え置き型": "STANDING_CONSOLE",
        "据え置き": "STANDING_CONSOLE",
        "PlayStation": "STANDING_CONSOLE",
        "Xbox": "STANDING_CONSOLE",
        "Wii": "STANDING_CONSOLE",
        # Portable Consoles (携帯型)
        "携帯型": "PORTABLE_CONSOLE",
        "携帯型ゲーム機": "PORTABLE_CONSOLE",
        "ポータブル": "PORTABLE_CONSOLE",
        "ゲームボーイ": "PORTABLE_CONSOLE",
        "Game Boy": "PORTABLE_CONSOLE",
        "PSP": "PORTABLE_CONSOLE",
        "PS Vita": "PORTABLE_CONSOLE",
        "3DS": "PORTABLE_CONSOLE",
        "DS": "PORTABLE_CONSOLE",
        # Hybrid Consoles (ハイブリッド型)
        "ハイブリッド": "HYBRID_CONSOLE",
        "ハイブリッド型": "HYBRID_CONSOLE",
        "Switch": "HYBRID_CONSOLE",
    }

    def extract_attributes(
        self,
        brand: str | None,
        name: str | None,
        code: str | None
    ) -> Dict:
        attributes = {}

        if brand:
            attributes["brand"] = brand

        if name:
            # Try to map Japanese subcategory to English enum
            for jp_term, eng_category in self.SUBCATEGORY_MAP.items():
                if jp_term in name:
                    attributes["subcategory"] = eng_category
                    break

            # Store raw subcategory name for debugging/future NLP
            attributes["subcategory_raw"] = name

        if code:
            # Model number from .item-code
            attributes["model_number"] = code

        return attributes


class StationaryExtractor(FieldExtractor):
    """
    Field extractor for Stationary products (writing utensils, fountain pens, office supplies).

    Hard-Off HTML structure for stationary:
    - .item-brand-name: Brand/Manufacturer (e.g., "Montblanc", "Parker", "Pilot", "Sailor")
    - .item-name: Product type/description (e.g., "万年筆", "ボールペン", "シャープペンシル")
    - .item-code: Model number (e.g., "Meisterstück 149", "Sonnet", "Custom 74")
    """

    # Japanese subcategory to English mapping
    SUBCATEGORY_MAP = {
        # Writing Utensils
        "筆記用具": "WRITING_UTENSIL",
        "筆記具": "WRITING_UTENSIL",
        # Fountain Pens
        "万年筆": "FOUNTAIN_PEN",
        "万年": "FOUNTAIN_PEN",
        "ファウンテンペン": "FOUNTAIN_PEN",
        # Ballpoint Pens
        "ボールペン": "BALLPOINT_PEN",
        "ボール": "BALLPOINT_PEN",
        # Mechanical Pencils
        "シャープペンシル": "MECHANICAL_PENCIL",
        "シャーペン": "MECHANICAL_PENCIL",
        # Pens (general)
        "ペン": "PEN",
        # Pencils
        "鉛筆": "PENCIL",
        # Markers
        "マーカー": "MARKER",
        "蛍光ペン": "MARKER",
        # Ink
        "インク": "INK",
        "インクボトル": "INK",
        # Notebooks
        "ノート": "NOTEBOOK",
        "手帳": "NOTEBOOK",
    }

    def extract_attributes(
        self,
        brand: str | None,
        name: str | None,
        code: str | None
    ) -> Dict:
        attributes = {}

        if brand:
            attributes["brand"] = brand

        if name:
            # Try to map Japanese subcategory to English enum
            for jp_term, eng_category in self.SUBCATEGORY_MAP.items():
                if jp_term in name:
                    attributes["subcategory"] = eng_category
                    break

            # Store raw subcategory name for debugging/future NLP
            attributes["subcategory_raw"] = name

        if code:
            # Model number from .item-code
            attributes["model_number"] = code

        return attributes


# Extractor registry - maps niche types to their extractors
FIELD_EXTRACTORS: Dict[str, FieldExtractor] = {
    "CAMERA_GEAR": CameraGearExtractor(),
    "WATCH": WatchExtractor(),
    "LUXURY_ITEM": LuxuryItemExtractor(),
    "VIDEOGAME": VideogameExtractor(),
    "STATIONARY": StationaryExtractor(),
}


# ============================================================================
# DATABASE SEEDING
# ============================================================================

@log_execution_time(logger)
def insert_market_listings(products_data: List[Dict], dry_run: bool = False) -> int:
    """
    Insert scraped products into MongoDB market_listings collection.

    Only inserts if the listing doesn't already exist (checks by _id).

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
            listing = create_hardoff_listing(
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
                if listing.attributes.get("condition_rank"):
                    print(f"Condition Rank: {listing.attributes['condition_rank']}")
                print(f"Attributes: {listing.attributes}")
                print(f"Listed At: {listing.listed_at}")
                print(f"Is Processed: {listing.is_processed}")
                print(f"{'='*70}")
                inserted_count += 1
            else:
                # Check if listing already exists (by ID or URL)
                # Convert HttpUrl to string for MongoDB query
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
        description="Hard-Off Marketplace Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to test scraping (no database writes)
  python hardoff_scraper.py --category watches --max-pages 2 --dry-run

  # Live run to scrape and save watches
  python hardoff_scraper.py --category watches --max-pages 5

  # Scrape camera gear
  python hardoff_scraper.py --category camera_gear --max-pages 10

  # Scrape luxury items (bags and wallets - includes subcategories)
  python hardoff_scraper.py --category luxury_items --max-pages 5

  # Filter by condition ranks (N=New, S=Nearly New, A=Excellent)
  python hardoff_scraper.py --category watches --ranks N S A --max-pages 5

  # Only scrape luxury items in excellent condition or better
  python hardoff_scraper.py --category luxury_items --ranks N S A --max-pages 10 --dry-run

  # Search by keyword (requires --niche and --keyword)
  python hardoff_scraper.py --niche VIDEOGAME --keyword "ゲームボーイ" --max-pages 5
  python hardoff_scraper.py --niche LUXURY_ITEM --keyword "LOUIS VUITTON" --ranks N S A --max-pages 10 --dry-run
        """
    )
    parser.add_argument(
        "--category",
        choices=list(CATEGORIES.keys()),
        help="Product category to scrape (mutually exclusive with --niche/--keyword)"
    )
    parser.add_argument(
        "--niche",
        choices=["WATCH", "CAMERA_GEAR", "LUXURY_ITEM", "POKEMON_CARD", "VIDEOGAME", "STATIONARY"],
        help="Niche type for keyword search (requires --keyword)"
    )
    parser.add_argument(
        "--keyword",
        type=str,
        help="Search keyword in Japanese or English (requires --niche)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Maximum number of pages to scrape (default: 5)"
    )
    parser.add_argument(
        "--ranks",
        nargs="+",
        choices=["N", "S", "A", "B", "C", "D", "JUNK"],
        help="Filter by condition ranks (e.g., --ranks N S A for New, Nearly New, Excellent)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate scraped data without saving to database"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.keyword and not args.niche:
        parser.error("--keyword requires --niche to be specified")
    if args.niche and not args.keyword:
        parser.error("--niche requires --keyword to be specified")
    if args.category and (args.niche or args.keyword):
        parser.error("--category cannot be used with --niche/--keyword")
    if not args.category and not (args.niche and args.keyword):
        parser.error("Either --category or (--niche and --keyword) must be specified")

    # Determine scraping mode
    if args.keyword:
        # Keyword search mode
        niche_type = args.niche
        display_name = f"Keyword Search: {args.keyword}"
        category_name = f"keyword:{args.keyword}"
    else:
        # Category browsing mode
        category_config = CATEGORIES[args.category]
        niche_type = category_config.niche_type
        display_name = category_config.display_name
        category_name = args.category

    # Log session start
    session_id = str(uuid.uuid4())[:8]
    logger.info("=" * 60)
    logger.info("VELODATA - HARD-OFF SCRAPER")
    logger.info("=" * 60)
    logger.info(
        "Starting scraper session",
        extra={
            "session_id": session_id,
            "category": category_name,
            "niche_type": niche_type,
            "keyword": args.keyword,
            "max_pages": args.max_pages,
            "ranks": args.ranks,
            "dry_run": args.dry_run,
        }
    )

    total_scraped = 0
    total_seeded = 0

    try:
        all_products = []

        if args.keyword:
            # Keyword search mode - single search query
            logger.info(
                f"Searching by keyword: {args.keyword}",
                extra={"session_id": session_id, "niche_type": niche_type}
            )

            products_data = scrape_hardoff_category(
                category_url="",  # Not used in keyword mode
                niche_type=niche_type,
                max_pages=args.max_pages,
                ranks=args.ranks,
                keyword=args.keyword,
                session_id=session_id
            )
            all_products.extend(products_data)
            logger.info(
                f"Keyword search yielded {len(products_data)} products",
                extra={"session_id": session_id, "keyword": args.keyword}
            )
        else:
            # Category browsing mode - scrape category URLs
            category_config = CATEGORIES[args.category]
            urls_to_scrape = [category_config.url]
            if category_config.subcategories:
                urls_to_scrape.extend(category_config.subcategories)
                logger.info(
                    f"Category has {len(category_config.subcategories)} subcategories",
                    extra={
                        "session_id": session_id,
                        "total_urls": len(urls_to_scrape)
                    }
                )

            # Scrape each URL
            for url_index, url in enumerate(urls_to_scrape, 1):
                logger.info(
                    f"Scraping URL {url_index}/{len(urls_to_scrape)}: {url}",
                    extra={"session_id": session_id}
                )

                products_data = scrape_hardoff_category(
                    category_url=url,
                    niche_type=category_config.niche_type,
                    max_pages=args.max_pages,
                    ranks=args.ranks,
                    keyword=None,
                    session_id=session_id
                )
                all_products.extend(products_data)
                logger.info(
                    f"URL {url_index} yielded {len(products_data)} products",
                    extra={"session_id": session_id, "url": url}
                )

        total_scraped = len(all_products)

        if all_products:
            inserted = insert_market_listings(all_products, dry_run=args.dry_run)
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
            "category": category_name,
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
