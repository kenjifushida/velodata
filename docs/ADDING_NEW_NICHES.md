# Quick Reference: Adding New Product Niches

**Last Updated:** 2025-01-02
**Reference Implementation:** STATIONARY niche

---

## Overview

This guide shows you how to add a new product niche to VeloData following production-grade patterns established in the STATIONARY implementation.

**Time to implement:** ~30-45 minutes for experienced developer
**Files to modify:** 8 files
**Difficulty:** Intermediate

---

## Step-by-Step Checklist

### ✅ Step 1: Update Python Data Model (2 minutes)

**File:** `core/models/market_listing.py`

```python
# Line ~195: Add niche to Literal type
niche_type: Literal[
    "POKEMON_CARD",
    "WATCH",
    "CAMERA_GEAR",
    "LUXURY_ITEM",
    "VIDEOGAME",
    "STATIONARY",
    "YOUR_NEW_NICHE"  # ← Add here
]
```

---

### ✅ Step 2: Update TypeScript Data Model (2 minutes)

**File:** `apps/dashboard/lib/models/market-listing.ts`

```typescript
// Line ~7: Add niche to union type
export type NicheType =
    | 'POKEMON_CARD'
    | 'WATCH'
    | 'CAMERA_GEAR'
    | 'LUXURY_ITEM'
    | 'VIDEOGAME'
    | 'STATIONARY'
    | 'YOUR_NEW_NICHE';  // ← Add here
```

---

### ✅ Step 3: Add Display Name to Constants (2 minutes)

**File:** `apps/dashboard/lib/constants.ts`

```typescript
// Line ~11: Add display name
export const NICHE_DISPLAY_NAMES: Record<NicheType, string> = {
  POKEMON_CARD: 'Pokemon Cards',
  WATCH: 'Watches',
  CAMERA_GEAR: 'Camera Gear',
  LUXURY_ITEM: 'Luxury Items',
  VIDEOGAME: 'Videogames',
  STATIONARY: 'Stationary',
  YOUR_NEW_NICHE: 'Your Display Name',  // ← Add here
} as const;
```

---

### ✅ Step 4: Configure Hard-Off Scraper (10-15 minutes)

**File:** `services/scrapers/hardoff_scraper.py`

#### 4a. Update CategoryConfig Literal Type (~Line 97)

```python
class CategoryConfig(BaseModel):
    url: str
    niche_type: Literal[
        "WATCH",
        "CAMERA_GEAR",
        "LUXURY_ITEM",
        "POKEMON_CARD",
        "VIDEOGAME",
        "STATIONARY",
        "YOUR_NEW_NICHE"  # ← Add here
    ]
    display_name: str
    subcategories: Optional[List[str]] = None
```

#### 4b. Add Category Configuration (~Line 133)

```python
CATEGORIES: Dict[str, CategoryConfig] = {
    # ... existing categories ...
    "your_new_niche": CategoryConfig(
        url="https://netmall.hardoff.co.jp/cate/YOUR_CATEGORY_ID/",
        niche_type="YOUR_NEW_NICHE",
        display_name="Your Display Name",
        subcategories=[
            "https://netmall.hardoff.co.jp/cate/SUBCATEGORY1/",
            "https://netmall.hardoff.co.jp/cate/SUBCATEGORY2/",
        ],  # ← Optional
    ),
}
```

#### 4c. Create Field Extractor Class (~Line 807)

```python
class YourNewNicheExtractor(FieldExtractor):
    """
    Field extractor for Your New Niche products.

    Hard-Off HTML structure:
    - .item-brand-name: Brand/Manufacturer
    - .item-name: Product type/description
    - .item-code: Model number
    """

    # Subcategory mapping (Japanese → English)
    SUBCATEGORY_MAP = {
        "日本語サブカテゴリ": "ENGLISH_SUBCATEGORY",
        # Add all subcategory mappings here
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
            # Map Japanese subcategory to English enum
            for jp_term, eng_category in self.SUBCATEGORY_MAP.items():
                if jp_term in name:
                    attributes["subcategory"] = eng_category
                    break

            attributes["subcategory_raw"] = name

        if code:
            attributes["model_number"] = code

        return attributes
```

#### 4d. Register Extractor (~Line 875)

```python
FIELD_EXTRACTORS: Dict[str, FieldExtractor] = {
    "CAMERA_GEAR": CameraGearExtractor(),
    "WATCH": WatchExtractor(),
    "LUXURY_ITEM": LuxuryItemExtractor(),
    "VIDEOGAME": VideogameExtractor(),
    "STATIONARY": StationaryExtractor(),
    "YOUR_NEW_NICHE": YourNewNicheExtractor(),  # ← Add here
}
```

#### 4e. Update Argparse Choices (~Line 1060)

```python
parser.add_argument(
    "--niche",
    choices=[
        "WATCH",
        "CAMERA_GEAR",
        "LUXURY_ITEM",
        "POKEMON_CARD",
        "VIDEOGAME",
        "STATIONARY",
        "YOUR_NEW_NICHE"  # ← Add here
    ],
    help="Niche type for keyword search (requires --keyword)"
)
```

#### 4f. Update Documentation (~Line 17)

```python
"""
Supported Categories:
    - watches: Luxury and vintage wristwatches
    - camera_gear: Digital cameras, lenses, and photography equipment
    - luxury_items: Designer bags, wallets, and accessories
    - videogames: Game consoles (standing, portable, hybrid)
    - stationary: Writing utensils, fountain pens, and office supplies
    - your_new_niche: Description of your new niche  # ← Add here
"""
```

---

### ✅ Step 5: Add eBay Export Support (10-15 minutes)

**File:** `apps/dashboard/app/actions/export.ts`

#### 5a. Add eBay Category Mapping (~Line 73)

```typescript
const EBAY_CATEGORIES: Record<string, string> = {
  WATCH: '31387',
  CAMERA_GEAR: '15230',
  POKEMON_CARD: '183454',
  LUXURY_ITEM: '169291',
  VIDEOGAME: '139971',
  STATIONARY: '159912',
  YOUR_NEW_NICHE: 'EBAY_CATEGORY_ID',  // ← Add here (find on eBay)
};
```

#### 5b. Add Subcategory Mapping (~Line 97)

```typescript
const YOUR_NEW_NICHE_SUBCATEGORY_CATEGORIES: Record<string, string> = {
  SUBCATEGORY_1: 'EBAY_CATEGORY_ID_1',
  SUBCATEGORY_2: 'EBAY_CATEGORY_ID_2',
  // Add all subcategory → eBay category mappings
};
```

#### 5c. Add Category Helper Function (~Line 129)

```typescript
function getYourNewNicheCategory(subcategory?: string): string {
  if (subcategory && YOUR_NEW_NICHE_SUBCATEGORY_CATEGORIES[subcategory]) {
    return YOUR_NEW_NICHE_SUBCATEGORY_CATEGORIES[subcategory];
  }
  return EBAY_CATEGORIES.YOUR_NEW_NICHE; // Default category
}
```

#### 5d. Update Category Selection Logic (~Line 397)

```typescript
let ebayCategory: string;
if (listing.niche_type === 'LUXURY_ITEM') {
  ebayCategory = getLuxuryItemCategory(attributes.subcategory);
} else if (listing.niche_type === 'VIDEOGAME') {
  ebayCategory = getVideogameCategory(attributes.subcategory);
} else if (listing.niche_type === 'STATIONARY') {
  ebayCategory = getStationaryCategory(attributes.subcategory);
} else if (listing.niche_type === 'YOUR_NEW_NICHE') {
  ebayCategory = getYourNewNicheCategory(attributes.subcategory);  // ← Add here
} else {
  ebayCategory = EBAY_CATEGORIES[listing.niche_type] || '15230';
}
```

#### 5e. Add Product Description (~Line 200)

```typescript
const nicheDescriptions: Record<string, string> = {
  WATCH: 'Authentic Pre-Owned Luxury Watch',
  CAMERA_GEAR: 'Professional Camera Equipment',
  POKEMON_CARD: 'Authentic Pokemon Trading Card',
  LUXURY_ITEM: 'Authentic Designer Luxury Item',
  VIDEOGAME: 'Authentic Game Console from Japan',
  STATIONARY: 'Authentic Writing Instrument from Japan',
  YOUR_NEW_NICHE: 'Your Product Description',  // ← Add here
};
```

---

## Testing Your Implementation

### 1. Test Scraper

```bash
# Activate virtual environment
source venv/bin/activate

# Test dry run
python hardoff_scraper.py --category your_new_niche --max-pages 1 --dry-run

# Test keyword search
python hardoff_scraper.py --niche YOUR_NEW_NICHE --keyword "検索キーワード" --max-pages 1 --dry-run

# Test live scraping (saves to database)
python hardoff_scraper.py --category your_new_niche --max-pages 1
```

### 2. Test Dashboard

```bash
# Build dashboard
cd apps/dashboard
npm run build

# Start development server
npm run dev

# Navigate to http://localhost:3000/dashboard
# 1. Filter by your new niche
# 2. Check stats card shows count
# 3. View listings in table
```

### 3. Test CSV Export

1. Select items from your new niche
2. Click "Export to eBay CSV"
3. Configure margin
4. Download CSV
5. Verify category IDs in CSV

---

## Common Pitfalls to Avoid

### ❌ Don't Do This

```typescript
// ❌ Hardcoding display names in components
const nicheNames = {
  YOUR_NEW_NICHE: 'Your Niche'
};

// ❌ Forgetting to update TypeScript types
// (Will cause compile errors)

// ❌ Using wrong eBay category IDs
// (eBay will reject your CSV)

// ❌ Not handling subcategories
// (Items will use default category)
```

### ✅ Do This Instead

```typescript
// ✅ Import from centralized constants
import { NICHE_DISPLAY_NAMES } from '@/lib/constants';

// ✅ Always update both Python and TypeScript types

// ✅ Research correct eBay categories on eBay.com

// ✅ Map all subcategories properly
```

---

## Finding eBay Category IDs

1. Go to [eBay Category Selector](https://www.ebay.com/sh/research)
2. Search for your product type
3. Navigate to the most specific category
4. Copy the category ID from the URL:
   ```
   https://www.ebay.com/b/Pens-Writing-Instruments/159912/bn_1643521
                                         ^^^^^^ ← This is the category ID
   ```
5. For item specifics, check [eBay Category Features](https://developer.ebay.com/devzone/xml/docs/reference/ebay/GetCategoryFeatures.html)

---

## Reference Implementation

See [`STATIONARY_IMPLEMENTATION.md`](../STATIONARY_IMPLEMENTATION.md) for a complete production-grade implementation example.

---

## Need Help?

**Common Issues:**
- TypeScript errors → Run `npm run type-check` in dashboard
- Python import errors → Check virtual environment is activated
- Scraper not finding items → Inspect Hard-Off HTML structure
- eBay CSV rejected → Verify category IDs and condition codes

**Documentation:**
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [LOGGING.md](LOGGING.md) - Logging guide
- [CLAUDE.md](../CLAUDE.md) - Claude Code reference

---

**Total Time:** ~30-45 minutes
**Difficulty:** Intermediate
**Last Updated:** 2025-01-02
