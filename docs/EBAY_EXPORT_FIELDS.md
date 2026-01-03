# eBay Export Fields Reference

**Last Updated:** 2025-01-02
**Version:** 2.0.0

---

## Overview

This document provides a comprehensive reference for all eBay File Exchange CSV fields used by VeloData's export functionality. Each niche has specific item-specific fields required by eBay.

**Key Principle:** eBay ignores unused fields in the CSV, so we include all possible fields for all niches in every export. Each niche populates only its relevant fields.

---

## Universal Fields (All Niches)

These fields are included in every export regardless of niche:

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `*Action(SiteID=US\|Country=US\|Currency=USD\|Version=1193)` | ✅ | Action type | `Add` |
| `*Category` | ✅ | eBay category ID | `31387` (Watches) |
| `*Title` | ✅ | Listing title (max 80 chars) | `Rolex Submariner 116610LN` |
| `*StartPrice` | ✅ | Item price in USD | `8450.25` |
| `*Quantity` | ✅ | Number of items | `1` |
| `*Format` | ✅ | Listing format | `FixedPrice` |
| `*Duration` | ✅ | Listing duration | `GTC` (Good 'Til Cancelled) |
| `*Location` | ✅ | Ship from location | `Tokyo, Japan` |
| `*Description` | ✅ | HTML description | `<div>...</div>` |
| `C:Brand` | ✅ | Brand name | `Rolex` |
| `Product:UPC` | ✅ | UPC code | `Does not apply` |
| `Product:ISBN` | ✅ | ISBN code | `Does not apply` |
| `PicURL` | ✅ | Image URLs (pipe-separated) | `https://...\|https://...` |
| `ConditionID` | ✅ | eBay condition code | `3000` (Used) |
| `C:Model` | ✅ | Model/reference number | `116610LN` |
| `C:Type` | ✅ | Product type | `Wristwatch` |
| `*ShippingType` | ✅ | Shipping type | `Flat` |
| `ShippingService-1:Option` | ✅ | Shipping service | `ShippingMethodStandard` |
| `ShippingService-1:Cost` | ✅ | Shipping cost | `0.00` (Free shipping) |
| `DispatchTimeMax` | ✅ | Days to ship | `7` |
| `ReturnsAcceptedOption` | ✅ | Returns accepted | `ReturnsAccepted` |
| `ReturnsWithinOption` | ✅ | Return window | `Days_30` |
| `RefundOption` | ✅ | Refund type | `MoneyBack` |
| `ShippingCostPaidByOption` | ✅ | Who pays return shipping | `Buyer` |

---

## Niche-Specific Fields

### 1. WATCH (Category: 31387 - Wristwatches)

**eBay Category:** [31387 - Wristwatches](https://www.ebay.com/b/Wristwatches/31387/bn_1643424)

| Field | Required | Default Value | Description |
|-------|----------|---------------|-------------|
| `C:Band Material` | Recommended | `Stainless Steel` | Watch band material |
| `C:Case Material` | Recommended | `Stainless Steel` | Watch case material |
| `C:Movement` | Recommended | `Automatic` | Movement type |
| `C:Dial Color` | Recommended | Extracted from title | Watch face color |

**Example CSV Row:**
```csv
Add,31387,Rolex Submariner 116610LN,8450.25,1,FixedPrice,GTC,"Tokyo, Japan",...,Rolex,...,Stainless Steel,Stainless Steel,Automatic,Black,...
```

---

### 2. CAMERA_GEAR (Category: 15230 - Digital Cameras)

**eBay Category:** [15230 - Digital Cameras](https://www.ebay.com/b/Digital-Cameras/15230/bn_1643420)

| Field | Required | Default Value | Description |
|-------|----------|---------------|-------------|
| `C:Series` | Recommended | First word of model | Camera series (e.g., "EOS") |
| `C:Megapixels` | Recommended | `See description` | Camera megapixels |
| `C:Optical Zoom` | Recommended | `See description` | Optical zoom specification |

**Example CSV Row:**
```csv
Add,15230,Canon EOS R5 Mirrorless Camera,2845.50,1,FixedPrice,GTC,"Tokyo, Japan",...,Canon,...,EOS,See description,See description,...
```

---

### 3. POKEMON_CARD (Category: 183454 - Pokemon TCG)

**eBay Category:** [183454 - Pokemon Trading Card Game](https://www.ebay.com/b/Pokemon-Individual-Cards/183454/bn_1643488)

| Field | Required | Default Value | Description |
|-------|----------|---------------|-------------|
| `C:Card Name` | Recommended | From title | Pokemon card name |
| `C:Card Number` | Recommended | From attributes | Card number in set |
| `C:Set` | Recommended | From attributes | Set code (e.g., "sv2a") |
| `C:Rarity` | Recommended | From attributes | Card rarity (e.g., "RR") |
| `C:Language` | Recommended | `Japanese` | Card language |

**Example CSV Row:**
```csv
Add,183454,Pikachu ex RR sv2a 165/165,45.75,1,FixedPrice,GTC,"Tokyo, Japan",...,Pokemon,...,Pikachu ex,165,sv2a,RR,Japanese,...
```

---

### 4. LUXURY_ITEM (Categories: 169291, 45258, 155183)

**eBay Categories:**
- [169291 - Women's Bags & Handbags](https://www.ebay.com/b/Womens-Bags-Handbags/169291/bn_1643471)
- [45258 - Women's Wallets](https://www.ebay.com/b/Womens-Wallets/45258/bn_1643459)
- [155183 - Women's Accessories](https://www.ebay.com/b/Womens-Accessories/155183/bn_1643465)

#### Subcategory: BAG (Category 169291)

| Field | Required | Default Value | Description |
|-------|----------|---------------|-------------|
| `C:Exterior Color` | ✅ | Extracted from title | Bag color |
| `C:Exterior Material` | ✅ | Based on brand | Bag material (Canvas/Leather) |
| `C:Department` | ✅ | `Women` | Department |
| `C:Style` | ✅ | `Shoulder Bag` | Bag style |

#### Subcategory: WALLET/ACCESSORY (Categories 45258, 155183)

| Field | Required | Default Value | Description |
|-------|----------|---------------|-------------|
| `Color` | ✅ | Extracted from title | Item color |
| `C:Department` | ✅ | `Women` | Department |
| `C:Style` | ✅ | Based on subcategory | Item style |

**Example CSV Row (Bag):**
```csv
Add,169291,Louis Vuitton Neverfull MM,1245.00,1,FixedPrice,GTC,"Tokyo, Japan",...,Louis Vuitton,...,Brown,Canvas,Women,Shoulder Bag,...
```

---

### 5. VIDEOGAME (Categories: 139971, 171831)

**eBay Categories:**
- [139971 - Video Game Consoles](https://www.ebay.com/b/Video-Game-Consoles/139971/bn_1643431)
- [171831 - Portable Gaming](https://www.ebay.com/b/Portable-Gaming/171831/bn_1643492)

| Field | Required | Default Value | Description |
|-------|----------|---------------|-------------|
| `C:Platform` | ✅ | Detected from brand/model | Gaming platform |
| `C:Type` | ✅ | `Console` | Product type |

**Platform Detection Logic:**
- Nintendo Switch → `Nintendo Switch`
- Game Boy (ゲームボーイ) → `Nintendo Game Boy`
- 3DS → `Nintendo 3DS`
- PlayStation → `Sony PlayStation`
- PSP → `Sony PSP`
- Xbox → `Microsoft Xbox`

**Example CSV Row:**
```csv
Add,171831,Nintendo Game Boy DGM-01,164.87,1,FixedPrice,GTC,"Tokyo, Japan",...,Nintendo,...,Nintendo Game Boy,Console,...
```

---

### 6. STATIONARY (Categories: 61778-61782, 49004, 159903)

**eBay Categories (LEAF categories - most specific):**
- [61778 - Fountain Pens](https://www.ebay.com/b/Fountain-Pens/61778/bn_16562212)
- [61782 - Ballpoint Pens](https://www.ebay.com/b/Ballpoint-Pens/61782/bn_16562216)
- [61780 - Mechanical Pencils](https://www.ebay.com/b/Mechanical-Pencils/61780/bn_16562214)
- [61779 - Pencils](https://www.ebay.com/b/Pencils/61779/bn_16562213)
- [61781 - Markers](https://www.ebay.com/b/Markers/61781/bn_16562215)
- [49004 - Ink](https://www.ebay.com/b/Collectible-Ink/49004/bn_16561979)
- [159903 - Notebooks & Pads](https://www.ebay.com/b/Paper-Notebooks-Pads/159903/bn_1643519)

**IMPORTANT:** Category 159912 (Pens & Writing Instruments) is a parent category and will be rejected by eBay with error "The category selected is not a leaf category". Always use the specific subcategories above.

#### For Pens (FOUNTAIN_PEN, BALLPOINT_PEN, PEN)

| Field | Required | Default Value | Description |
|-------|----------|---------------|-------------|
| `C:Ink Color` | Recommended | `Black` | Ink color |
| `C:Point Size` | Recommended | `Medium` | Pen point size |
| `C:Features` | Recommended | `Refillable` (fountain pens) | Pen features |

**Example CSV Row:**
```csv
Add,61778,Montblanc Meisterstück 149,245.67,1,FixedPrice,GTC,"Tokyo, Japan",...,Montblanc,...,Black,Medium,Refillable,...
```

---

## eBay Condition IDs

Different niche categories accept different condition IDs:

### Standard Condition IDs
Used by: WATCH, CAMERA_GEAR, POKEMON_CARD

| Japanese Rank | Condition | eBay ID | Description |
|---------------|-----------|---------|-------------|
| N | New | `1000` | New |
| S | Nearly New | `1500` | New other (see details) |
| A | Excellent | `3000` | Used - Excellent |
| B | Good | `4000` | Used - Very Good |
| C | Fair | `5000` | Used - Good |
| D | Poor | `6000` | Used - Acceptable |
| JUNK | Junk | `7000` | For parts or not working |

### Luxury Items Condition IDs
Used by: LUXURY_ITEM

| Japanese Rank | Condition | eBay ID | Description |
|---------------|-----------|---------|-------------|
| N | New | `1000` | New with tags |
| S | Nearly New | `1500` | New without tags |
| A | Excellent | `1750` | New with defects |
| B, C, D, JUNK | Pre-owned | `3000` | Pre-owned |

### Videogames Condition IDs
Used by: VIDEOGAME, STATIONARY

| Japanese Rank | Condition | eBay ID | Description |
|---------------|-----------|---------|-------------|
| N | New | `1000` | New |
| S | Nearly New | `1500` | New other (see details) |
| A, B, C, D | Used | `3000` | Used |
| JUNK | Junk | `7000` | For parts or not working |

---

## Pricing Model

**All Niches Use Free Shipping Model:**

1. **Cost Calculation:**
   ```
   Base Cost (JPY → USD) + $30 Shipping = Total Cost
   ```

2. **Margin Calculation:**
   ```
   Sale Price = (Total Cost + Desired Profit + $0.30) / (1 - 17.25%)
   ```

3. **eBay Fees (17.25% + $0.30):**
   - Final Value Fee: 13.25%
   - Payment Processing: 2.35% + $0.30
   - International Fee: 1.65%

4. **Buyer Sees:**
   - Item Price: Calculated sale price
   - Shipping: FREE (included in price)

---

## CSV Export Example

**Sample export with multiple niches:**

```csv
*Action(SiteID=US|Country=US|Currency=USD|Version=1193),*Category,*Title,*StartPrice,...,C:Platform,C:Band Material,C:Card Name,...
Add,31387,Rolex Submariner 116610LN,8450.25,...,,Stainless Steel,,...
Add,159912,Montblanc Meisterstück 149,245.67,...,,,,...
Add,171831,Nintendo Game Boy DGM-01,164.87,...,Nintendo Game Boy,,,...
Add,183454,Pikachu ex RR sv2a 165/165,45.75,...,,,Pikachu ex,...
```

**Note:** Empty cells for unused fields are normal. eBay ignores fields that don't apply to the category.

---

## How to Find eBay Category IDs

1. **Navigate to eBay Category:**
   - Go to [eBay.com](https://www.ebay.com)
   - Browse to the specific category for your product
   - Example: Collectibles > Trading Cards > Pokemon

2. **Extract Category ID from URL:**
   ```
   https://www.ebay.com/b/Pokemon-Individual-Cards/183454/bn_1643488
                                                    ^^^^^^
                                                    This is the category ID
   ```

3. **Verify Category Features:**
   - Use [eBay Category Features API](https://developer.ebay.com/devzone/xml/docs/reference/ebay/GetCategoryFeatures.html)
   - Or manually test with File Exchange

---

## Common eBay Upload Errors

### Error: The category selected is not a leaf category
**Cause:** Using a parent category ID instead of a specific leaf category
**Example:** Using 159912 (Pens & Writing Instruments) instead of 61778 (Fountain Pens)
**Solution:** Use the most specific category ID available. Parent categories are not allowed.
- ❌ 159912 (Pens & Writing Instruments) - Parent category
- ✅ 61778 (Fountain Pens) - Leaf category

### Error: Invalid Condition ID
**Cause:** Using wrong condition ID for category
**Solution:** Check condition ID mapping for that niche (VIDEOGAME and STATIONARY only accept 1000, 1500, 3000, 7000)

### Error: Missing Required Field
**Cause:** Required item-specific field not populated
**Solution:** Add field to niche-specific logic in `export.ts`

### Error: Invalid Category ID
**Cause:** Wrong category ID for product type
**Solution:** Verify category ID on eBay.com

---

## Future Enhancements

### Planned Improvements
- [ ] Parse watch movement from title (Automatic/Quartz/Manual)
- [ ] Extract camera megapixels from specifications
- [ ] Parse pen nib size from model number
- [ ] Add watch band color detection
- [ ] Implement camera lens mount detection
- [ ] Add watch case size (mm) extraction

### Additional Niches to Support
- [ ] Sneakers
- [ ] Designer Clothing
- [ ] Vintage Toys
- [ ] Collectible Coins
- [ ] Fine Jewelry

---

## References

- [eBay File Exchange Documentation](https://www.ebay.com/help/selling/listings/creating-managing-listings/add-edit-items-file-exchange)
- [eBay Category IDs](https://pages.ebay.com/sellerinformation/growing/categorychanges/categoryids.html)
- [eBay Condition IDs](https://developer.ebay.com/devzone/xml/docs/reference/ebay/types/ConditionIDType.html)
- [eBay Item Specifics](https://developer.ebay.com/devzone/xml/docs/reference/ebay/GetCategorySpecifics.html)

---

**Document Version:** 2.0.0
**Last Updated:** 2025-01-02
**Maintained By:** VeloData Engineering Team
