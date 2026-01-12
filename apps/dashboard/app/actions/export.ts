/**
 * Server Actions for eBay CSV Export
 *
 * Handles exporting market listings to eBay File Exchange CSV format.
 * Reference: https://www.ebay.com/help/selling/listings/creating-managing-listings/add-edit-items-file-exchange
 */
'use server';

import { getDatabase } from '@/lib/mongodb';
import type { MarketListing } from '@/lib/models/market-listing';

/**
 * eBay File Exchange CSV fields
 * Required fields marked with *
 */
interface EBayCSVRow {
  // Required fields
  '*Action(SiteID=US|Country=US|Currency=USD|Version=1193)': string;
  '*Category': string;
  '*Title': string;
  '*StartPrice': string;
  '*Quantity': string;
  '*Format': string;
  '*Duration': string;
  '*Location': string;
  '*Description': string;

  // Product identifiers
  'C:Brand': string;
  'Product:UPC': string;
  'Product:ISBN': string;

  // Images (eBay supports up to 12 images, pipe-separated in single PicURL field)
  'PicURL': string;

  // Item specifics
  'ConditionID': string;
  'C:Model': string;
  'C:Type': string;

  // Luxury item specifics (category-dependent)
  'C:Exterior Color'?: string;  // Required for bags (169291)
  'C:Exterior Material'?: string;  // Required for bags (169291)
  'C:Department'?: string;  // Required for bags (169291)
  'C:Style'?: string;  // Required for bags (169291)
  'Color'?: string;  // Required for wallets (45258) and accessories (155183)

  // Videogame console specifics (category-dependent)
  'C:Platform'?: string;  // Required for game consoles (139971, 171831)

  // Watch specifics (category-dependent)
  'C:Band Material'?: string;  // For watches (31387)
  'C:Case Material'?: string;  // For watches (31387)
  'C:Movement'?: string;  // For watches (31387)
  'C:Dial Color'?: string;  // For watches (31387)

  // Camera specifics (category-dependent)
  'C:Series'?: string;  // For cameras (15230)
  'C:Megapixels'?: string;  // For digital cameras (15230)
  'C:Optical Zoom'?: string;  // For cameras (15230)

  // Pokemon Card specifics (category-dependent)
  'C:Card Name'?: string;  // For Pokemon cards (183454)
  'C:Card Number'?: string;  // For Pokemon cards (183454)
  'C:Set'?: string;  // For Pokemon cards (183454)
  'C:Rarity'?: string;  // For Pokemon cards (183454)
  'C:Language'?: string;  // For Pokemon cards (183454)

  // Stationary specifics (category-dependent)
  'C:Ink Color'?: string;  // For pens (61778-61782)
  'C:Point Size'?: string;  // For pens (61778-61782)
  'C:Features'?: string;  // For stationary (61778-61782)

  // Collection Figures specifics (category-dependent)
  'C:Character'?: string;  // For action figures (261068)
  'C:Character Family'?: string;  // For action figures (261068)
  'C:Scale'?: string;  // For action figures (261068)
  'C:Material'?: string;  // For action figures (261068)

  // Shipping
  '*ShippingType': string;
  'ShippingService-1:Option': string;
  'ShippingService-1:Cost': string;
  'DispatchTimeMax': string;

  // Returns
  'ReturnsAcceptedOption': string;
  'ReturnsWithinOption': string;
  'RefundOption': string;
  'ShippingCostPaidByOption': string;
}

/**
 * eBay category mapping by niche type
 */
const EBAY_CATEGORIES: Record<string, string> = {
  WATCH: '31387', // Wristwatches
  CAMERA_GEAR: '15230', // Digital Cameras
  TCG: '183454', // Trading Card Games (default: Pokemon)
  LUXURY_ITEM: '169291', // Women's Bags & Handbags (default)
  VIDEOGAME: '139971', // Video Game Consoles (default)
  STATIONARY: '61778', // Fountain Pens (default - leaf category)
  COLLECTION_FIGURES: '261068', // Anime & Manga Action Figures
};

/**
 * eBay category mapping for TCG games
 */
const TCG_GAME_CATEGORIES: Record<string, string> = {
  POKEMON: '183454', // Pokemon Trading Card Game
  YUGIOH: '183444', // Yu-Gi-Oh! Trading Card Game
  ONE_PIECE: '183454', // One Piece TCG (use Pokemon category as proxy)
  MAGIC: '38292', // Magic: The Gathering Trading Card Game
};

/**
 * eBay category mapping for luxury item subcategories
 */
const LUXURY_SUBCATEGORY_CATEGORIES: Record<string, string> = {
  BAG: '169291', // Women's Bags & Handbags
  WALLET: '45258', // Women's Accessories > Wallets
  ACCESSORY: '155183', // Women's Accessories
};

/**
 * eBay category mapping for videogame console subcategories
 */
const VIDEOGAME_SUBCATEGORY_CATEGORIES: Record<string, string> = {
  STANDING_CONSOLE: '139971', // Video Game Consoles (home consoles like PlayStation, Xbox, Nintendo)
  PORTABLE_CONSOLE: '171831', // Portable Gaming (Game Boy, PSP, Nintendo DS, PS Vita)
  HYBRID_CONSOLE: '139971', // Video Game Consoles (Nintendo Switch - hybrid but listed as home console)
};

/**
 * eBay category mapping for stationary subcategories
 * NOTE: These are LEAF categories (most specific). Category 159912 is too broad and will be rejected.
 */
const STATIONARY_SUBCATEGORY_CATEGORIES: Record<string, string> = {
  FOUNTAIN_PEN: '61778', // Collectibles > Pens & Writing Instruments > Pens > Fountain Pens
  BALLPOINT_PEN: '61782', // Collectibles > Pens & Writing Instruments > Pens > Ballpoint Pens
  MECHANICAL_PENCIL: '61780', // Collectibles > Pens & Writing Instruments > Pens > Mechanical Pencils
  PEN: '61778', // Default to Fountain Pens for generic pens
  WRITING_UTENSIL: '61778', // Default to Fountain Pens for generic writing utensils
  PENCIL: '61779', // Collectibles > Pens & Writing Instruments > Pens > Pencils
  MARKER: '61781', // Collectibles > Pens & Writing Instruments > Pens > Markers
  INK: '49004', // Collectibles > Pens & Writing Instruments > Ink
  NOTEBOOK: '159903', // Office Products > Paper, Notebooks & Pads
};

/**
 * Get eBay category for a TCG card based on game
 */
function getTCGCategory(game?: string): string {
  if (game && TCG_GAME_CATEGORIES[game]) {
    return TCG_GAME_CATEGORIES[game];
  }
  return EBAY_CATEGORIES.TCG; // Default to Pokemon category
}

/**
 * Get eBay category for a luxury item based on subcategory
 */
function getLuxuryItemCategory(subcategory?: string): string {
  if (subcategory && LUXURY_SUBCATEGORY_CATEGORIES[subcategory]) {
    return LUXURY_SUBCATEGORY_CATEGORIES[subcategory];
  }
  return EBAY_CATEGORIES.LUXURY_ITEM; // Default to bags category
}

/**
 * Get eBay category for a videogame item based on subcategory
 */
function getVideogameCategory(subcategory?: string): string {
  if (subcategory && VIDEOGAME_SUBCATEGORY_CATEGORIES[subcategory]) {
    return VIDEOGAME_SUBCATEGORY_CATEGORIES[subcategory];
  }
  return EBAY_CATEGORIES.VIDEOGAME; // Default to video game consoles
}

/**
 * Get eBay category for a stationary item based on subcategory
 */
function getStationaryCategory(subcategory?: string): string {
  if (subcategory && STATIONARY_SUBCATEGORY_CATEGORIES[subcategory]) {
    return STATIONARY_SUBCATEGORY_CATEGORIES[subcategory];
  }
  return EBAY_CATEGORIES.STATIONARY; // Default to pens & writing instruments
}

/**
 * eBay Condition ID Mapping Strategy
 *
 * Different eBay categories have different allowed condition IDs.
 * This configuration maps each niche to its allowed condition mapping.
 */
type ConditionMapping = Record<string, string>;

const CONDITION_MAPPINGS: Record<string, ConditionMapping> = {
  // Standard condition mapping (Used by: TCG, WATCH, CAMERA_GEAR)
  STANDARD: {
    N: '1000',    // New
    S: '1500',    // New other (see details)
    A: '3000',    // Used - Excellent
    B: '4000',    // Used - Very Good
    C: '5000',    // Used - Good
    D: '6000',    // Used - Acceptable
    JUNK: '7000', // For parts or not working
  },

  // Luxury items have unique condition requirements
  // eBay luxury/fashion categories only accept: 1000, 1500, 1750, 3000
  LUXURY_ITEM: {
    N: '1000',    // New with tags
    S: '1500',    // New without tags
    A: '1750',    // New with defects
    B: '3000',    // Pre-owned
    C: '3000',    // Pre-owned
    D: '3000',    // Pre-owned
    JUNK: '3000', // Pre-owned (eBay doesn't allow "parts/not working" for luxury)
  },

  // Restricted condition mapping for collectibles and electronics
  // eBay categories only accept: 1000, 1500, 3000, 7000
  // Used by: VIDEOGAME, STATIONARY, COLLECTION_FIGURES
  RESTRICTED: {
    N: '1000',    // New
    S: '1500',    // New other (see details)
    A: '3000',    // Used
    B: '3000',    // Used (4000 not allowed)
    C: '3000',    // Used (5000 not allowed)
    D: '3000',    // Used (6000 not allowed)
    JUNK: '7000', // For parts or not working
  },
};

/**
 * Maps niche types to their condition mapping strategy
 */
const NICHE_CONDITION_STRATEGY: Record<string, keyof typeof CONDITION_MAPPINGS> = {
  TCG: 'STANDARD',
  WATCH: 'STANDARD',
  CAMERA_GEAR: 'STANDARD',
  LUXURY_ITEM: 'LUXURY_ITEM',
  VIDEOGAME: 'RESTRICTED',
  STATIONARY: 'RESTRICTED',
  COLLECTION_FIGURES: 'RESTRICTED',
};

/**
 * Map condition rank to eBay condition ID
 *
 * @param rank - Condition rank from Hard-Off (N, S, A, B, C, D, JUNK)
 * @param nicheType - Product niche type
 * @returns eBay condition ID
 */
function mapToEBayCondition(rank?: string, nicheType?: string): string {
  const strategy = nicheType ? NICHE_CONDITION_STRATEGY[nicheType] : 'STANDARD';
  const conditionMap = CONDITION_MAPPINGS[strategy] || CONDITION_MAPPINGS.STANDARD;

  return rank ? (conditionMap[rank] || '3000') : '3000';
}

/**
 * Generate eBay-compliant product description
 */
function generateEBayDescription(listing: MarketListing): string {
  const nicheDescriptions: Record<string, string> = {
    WATCH: 'Authentic Pre-Owned Luxury Watch',
    CAMERA_GEAR: 'Professional Camera Equipment',
    TCG: 'Authentic Trading Card Game Card',
    LUXURY_ITEM: 'Authentic Designer Luxury Item',
    VIDEOGAME: 'Authentic Game Console from Japan',
    STATIONARY: 'Authentic Writing Instrument from Japan',
    COLLECTION_FIGURES: 'Authentic Collectible Figure from Japan',
  };

  const title = nicheDescriptions[listing.niche_type] || 'Authentic Pre-Owned Item';

  // eBay allows HTML in descriptions
  const description = `
<div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
  <h2>${title}</h2>

  <p><strong>Sourced and Shipped from Japan</strong></p>

  <h3>Item Details</h3>
  <ul>
    <li><strong>Condition:</strong> ${mapConditionToText(listing.attributes.condition_rank)}</li>
  </ul>

  <h3>Shipping & Packaging</h3>
  <p>All items are carefully inspected, authenticated, and securely packaged with bubble wrap and
  protective materials to ensure safe international delivery.</p>

  <p><em>All items are sold as-is. Please review the condition grade and photos carefully before purchase.</em></p>
</div>
  `.trim();

  return description;
}

/**
 * Map condition rank to human-readable text
 */
function mapConditionToText(rank?: string): string {
  const conditionMap: Record<string, string> = {
    N: 'New - Brand new, unused item',
    S: 'Like New - Minimal to no signs of wear',
    A: 'Excellent - Light signs of use, well maintained',
    B: 'Very Good - Some signs of use, fully functional',
    C: 'Good - Noticeable wear, fully functional',
    D: 'Fair - Heavy wear, fully functional',
    JUNK: 'For Parts/Not Working - May not be functional',
  };

  return rank ? (conditionMap[rank] || 'Used') : 'Used';
}

/**
 * Map subcategory to eBay style for luxury items
 */
function mapSubcategoryToStyle(subcategory?: string): string {
  const styleMap: Record<string, string> = {
    BAG: 'Shoulder Bag',
    WALLET: 'Wallet',
    ACCESSORY: 'Fashion Accessory',
  };

  return subcategory ? (styleMap[subcategory] || 'Shoulder Bag') : 'Shoulder Bag';
}

/**
 * Determine exterior material based on brand and title
 * Most luxury brands use leather, but some use canvas (Louis Vuitton, Gucci)
 */
function determineExteriorMaterial(brand?: string, title?: string): string {
  const brandLower = brand?.toLowerCase() || '';
  const titleLower = title?.toLowerCase() || '';

  // Canvas-heavy brands
  if (
    brandLower.includes('louis vuitton') ||
    brandLower.includes('gucci') ||
    titleLower.includes('canvas')
  ) {
    return 'Canvas';
  }

  // Default to leather for luxury items
  return 'Leather';
}

/**
 * Determine primary color from product title and brand
 * eBay requires specific color values, not "Multicolor"
 *
 * Common luxury brand color patterns are checked first, then fallback to common colors
 */
function determineColor(brand?: string, title?: string): string {
  const titleLower = title?.toLowerCase() || '';
  const brandLower = brand?.toLowerCase() || '';

  // Color keyword mapping - order matters (more specific first)
  const colorPatterns: Record<string, string> = {
    // Specific shades first
    'navy': 'Blue',
    'beige': 'Beige',
    'tan': 'Beige',
    'burgundy': 'Red',
    'rose': 'Pink',
    'blush': 'Pink',
    'cognac': 'Brown',
    'camel': 'Brown',
    'khaki': 'Beige',
    'cream': 'White',
    'ivory': 'White',
    'silver': 'Silver',
    'gold': 'Gold',
    'metallic': 'Silver',

    // Basic colors
    'black': 'Black',
    'white': 'White',
    'brown': 'Brown',
    'red': 'Red',
    'blue': 'Blue',
    'green': 'Green',
    'pink': 'Pink',
    'purple': 'Purple',
    'yellow': 'Yellow',
    'orange': 'Orange',
    'gray': 'Gray',
    'grey': 'Gray',
  };

  // Check title for color keywords
  for (const [pattern, color] of Object.entries(colorPatterns)) {
    if (titleLower.includes(pattern)) {
      return color;
    }
  }

  // Brand-specific defaults based on common colorways
  if (brandLower.includes('louis vuitton')) {
    return 'Brown'; // Classic monogram canvas is brown
  }
  if (brandLower.includes('gucci')) {
    return 'Brown'; // GG canvas is typically brown/beige
  }
  if (brandLower.includes('chanel')) {
    return 'Black'; // Classic Chanel is often black
  }
  if (brandLower.includes('hermes') || brandLower.includes('hermès')) {
    return 'Brown'; // Classic Hermès is often brown/tan
  }

  // Default fallback - Brown is safe for most luxury leather goods
  return 'Brown';
}

/**
 * eBay fee structure
 */
const EBAY_FINAL_VALUE_FEE = 0.1325; // 13.25%
const EBAY_PAYMENT_PROCESSING_PERCENT = 0.0235; // 2.35%
const EBAY_PAYMENT_PROCESSING_FIXED = 0.30; // $0.30
const EBAY_INTERNATIONAL_FEE = 0.0165; // 1.65%
const JPY_TO_USD_RATE = 0.0067; // Exchange rate

/**
 * Shipping costs by niche type (FedEx International)
 * Collection Figures are larger/heavier, requiring higher shipping cost
 */
const SHIPPING_COSTS_BY_NICHE: Record<string, number> = {
  TCG: 30.0,
  WATCH: 30.0,
  CAMERA_GEAR: 30.0,
  LUXURY_ITEM: 30.0,
  VIDEOGAME: 30.0,
  STATIONARY: 30.0,
  COLLECTION_FIGURES: 46.9, // ¥7,000 JPY = $46.90 USD (higher due to size/weight)
};

/**
 * Get shipping cost for a specific niche type
 */
function getShippingCost(nicheType: string): number {
  return SHIPPING_COSTS_BY_NICHE[nicheType] || 30.0;
}

/**
 * Calculate sale price to achieve desired net margin after eBay fees
 *
 * @param costUSD - Item cost in USD
 * @param desiredMarginPercent - Desired net profit margin (e.g., 25 for 25%)
 * @param shippingCost - Shipping cost in USD (varies by niche)
 * @returns Sale price that achieves the desired net margin
 */
function calculateSalePriceWithMargin(costUSD: number, desiredMarginPercent: number, shippingCost: number): number {
  const totalFeePercent =
    EBAY_FINAL_VALUE_FEE + EBAY_PAYMENT_PROCESSING_PERCENT + EBAY_INTERNATIONAL_FEE;

  const desiredProfit = costUSD * (desiredMarginPercent / 100);

  const salePrice =
    (costUSD + shippingCost + desiredProfit + EBAY_PAYMENT_PROCESSING_FIXED) /
    (1 - totalFeePercent);

  return salePrice;
}

/**
 * Convert market listing to eBay CSV row
 *
 * @param listing - Market listing to convert
 * @param netMarginPercent - Desired net profit margin after fees (default 25%)
 */
function listingToEBayRow(listing: MarketListing, netMarginPercent: number = 25): EBayCSVRow {
  const { attributes } = listing;

  // Convert JPY to USD
  const costUSD = listing.price_jpy * JPY_TO_USD_RATE;

  // Get niche-specific shipping cost
  const shippingCost = getShippingCost(listing.niche_type);

  // Calculate sale price with desired net margin
  const priceUSD = calculateSalePriceWithMargin(costUSD, netMarginPercent, shippingCost).toFixed(2);

  // Determine eBay category (use subcategory for luxury items, videogames, stationary, and game for TCG)
  let ebayCategory: string;
  if (listing.niche_type === 'TCG') {
    ebayCategory = getTCGCategory(attributes.game);
  } else if (listing.niche_type === 'LUXURY_ITEM') {
    ebayCategory = getLuxuryItemCategory(attributes.subcategory);
  } else if (listing.niche_type === 'VIDEOGAME') {
    ebayCategory = getVideogameCategory(attributes.subcategory);
  } else if (listing.niche_type === 'STATIONARY') {
    ebayCategory = getStationaryCategory(attributes.subcategory);
  } else {
    ebayCategory = EBAY_CATEGORIES[listing.niche_type] || '15230';
  }

  const row: EBayCSVRow = {
    // Required fields
    '*Action(SiteID=US|Country=US|Currency=USD|Version=1193)': 'Add',
    '*Category': ebayCategory,
    '*Title': listing.title.substring(0, 80), // eBay title limit is 80 characters
    '*StartPrice': priceUSD,
    '*Quantity': '1',
    '*Format': 'FixedPrice',
    '*Duration': 'GTC', // Good 'Til Cancelled
    '*Location': 'Tokyo, Japan',
    '*Description': generateEBayDescription(listing),

    // Product identifiers
    'C:Brand': attributes.brand || 'Unbranded',
    'Product:UPC': 'Does not apply',
    'Product:ISBN': 'Does not apply',

    // Images (eBay supports up to 12 images, pipe-separated)
    'PicURL': listing.image_urls.slice(0, 12).join('|'),

    // Item specifics
    'ConditionID': mapToEBayCondition(attributes.condition_rank, listing.niche_type),
    'C:Model': attributes.model || attributes.model_number || attributes.reference_number || 'See description',
    'C:Type': attributes.subcategory || listing.niche_type,

    // Shipping
    '*ShippingType': 'Flat',
    'ShippingService-1:Option': 'ShippingMethodStandard',
    'ShippingService-1:Cost': '0.00', // Free shipping (cost included in item price)
    'DispatchTimeMax': '7', // 7 business days to ship

    // Returns
    'ReturnsAcceptedOption': 'ReturnsAccepted',
    'ReturnsWithinOption': 'Days_30',
    'RefundOption': 'MoneyBack',
    'ShippingCostPaidByOption': 'Buyer',
  };

  // Add niche-specific item specifics
  if (listing.niche_type === 'LUXURY_ITEM') {
    const subcategory = attributes.subcategory;

    if (subcategory === 'BAG') {
      // Category 169291 (Women's Bags & Handbags) - uses C:Exterior Color
      row['C:Exterior Color'] = determineColor(attributes.brand, listing.title);
      row['C:Exterior Material'] = determineExteriorMaterial(attributes.brand, listing.title);
      row['C:Department'] = 'Women';
      row['C:Style'] = 'Shoulder Bag';
    } else if (subcategory === 'WALLET' || subcategory === 'ACCESSORY') {
      // Categories 45258 (Wallets) and 155183 (Accessories) - use Color (not C:Exterior Color)
      row['Color'] = determineColor(attributes.brand, listing.title);
      row['C:Department'] = 'Women';
      row['C:Style'] = mapSubcategoryToStyle(subcategory);
    } else {
      // Default to bag fields if subcategory is unknown
      row['C:Exterior Color'] = determineColor(attributes.brand, listing.title);
      row['C:Exterior Material'] = determineExteriorMaterial(attributes.brand, listing.title);
      row['C:Department'] = 'Women';
      row['C:Style'] = 'Shoulder Bag';
    }
  } else if (listing.niche_type === 'VIDEOGAME') {
    // Videogame consoles - Categories 139971 (Video Game Consoles) and 171831 (Portable Gaming)
    // Both categories use C:Platform as a required field
    // Common platforms: Nintendo Game Boy, Nintendo Switch, Sony PlayStation, etc.
    const brand = attributes.brand || '';
    const modelNumber = attributes.model_number || '';

    // Determine platform from brand and model
    let platform = 'See description';
    if (brand.toLowerCase().includes('nintendo')) {
      if (modelNumber.toLowerCase().includes('switch')) {
        platform = 'Nintendo Switch';
      } else if (modelNumber.toLowerCase().includes('game boy') || modelNumber.toLowerCase().includes('ゲームボーイ')) {
        platform = 'Nintendo Game Boy';
      } else if (modelNumber.toLowerCase().includes('3ds')) {
        platform = 'Nintendo 3DS';
      } else if (modelNumber.toLowerCase().includes('ds')) {
        platform = 'Nintendo DS';
      } else if (modelNumber.toLowerCase().includes('wii')) {
        platform = 'Nintendo Wii';
      } else {
        platform = 'Nintendo';
      }
    } else if (brand.toLowerCase().includes('sony')) {
      if (modelNumber.toLowerCase().includes('playstation') || modelNumber.toLowerCase().includes('ps')) {
        platform = 'Sony PlayStation';
      } else if (modelNumber.toLowerCase().includes('psp')) {
        platform = 'Sony PSP';
      } else if (modelNumber.toLowerCase().includes('vita')) {
        platform = 'Sony PlayStation Vita';
      } else {
        platform = 'Sony PlayStation';
      }
    } else if (brand.toLowerCase().includes('microsoft')) {
      platform = 'Microsoft Xbox';
    } else if (brand.toLowerCase().includes('sega')) {
      platform = 'Sega';
    }

    row['C:Platform'] = platform;
    row['C:Type'] = 'Console';
  } else if (listing.niche_type === 'WATCH') {
    // Watches - Category 31387 (Wristwatches)
    // Common item specifics: Band Material, Case Material, Movement, Dial Color
    row['C:Band Material'] = 'Stainless Steel'; // Default, could be extracted from title
    row['C:Case Material'] = 'Stainless Steel';
    row['C:Movement'] = 'Automatic'; // Default for luxury watches
    row['C:Dial Color'] = determineColor(attributes.brand, listing.title);
  } else if (listing.niche_type === 'CAMERA_GEAR') {
    // Camera Gear - Category 15230 (Digital Cameras)
    // Item specifics: Series, Megapixels, Optical Zoom
    const brand = attributes.brand || '';
    const modelNumber = attributes.model_number || '';

    row['C:Series'] = modelNumber.split(' ')[0] || 'See description'; // e.g., "EOS" from "EOS R5"
    row['C:Megapixels'] = 'See description'; // Would need to parse from title/specs
    row['C:Optical Zoom'] = 'See description';
  } else if (listing.niche_type === 'TCG') {
    // Trading Card Games - Categories vary by game (Pokemon, Yu-Gi-Oh!, One Piece, Magic)
    // Item specifics: Card Name, Card Number, Set, Rarity, Language
    row['C:Card Name'] = listing.title.substring(0, 50);
    row['C:Card Number'] = attributes.card_number || 'See description';
    row['C:Set'] = attributes.set_code || attributes.set || 'See description';
    row['C:Rarity'] = attributes.rarity || 'See description';
    row['C:Language'] = attributes.language || 'Japanese'; // Default for Japanese marketplace
  } else if (listing.niche_type === 'STATIONARY') {
    // Stationary - Category 159912 (Pens & Writing Instruments)
    // Item specifics: Ink Color, Point Size, Features
    const modelNumber = attributes.model_number || '';
    const subcategory = attributes.subcategory || '';

    if (subcategory === 'FOUNTAIN_PEN' || subcategory === 'BALLPOINT_PEN' || subcategory === 'PEN') {
      row['C:Ink Color'] = 'Black'; // Default
      row['C:Point Size'] = 'Medium';
      row['C:Features'] = subcategory === 'FOUNTAIN_PEN' ? 'Refillable' : 'See description';
    }
  } else if (listing.niche_type === 'COLLECTION_FIGURES') {
    // Collection Figures item specifics
    const subcategory = attributes.subcategory || '';
    const characterName = attributes.character_name || '';

    // Character name from scraped data
    if (characterName) {
      row['C:Character'] = characterName;
    }

    // Character Family (e.g., "Anime", "Manga", etc.) - infer from brand or use generic
    const brand = attributes.brand || '';
    if (brand.toLowerCase().includes('bandai') || brand.toLowerCase().includes('good smile')) {
      row['C:Character Family'] = 'Anime';
    } else {
      row['C:Character Family'] = 'See description';
    }

    // Scale - common for figure types
    if (subcategory === 'SCALE_FIGURE') {
      row['C:Scale'] = '1:8'; // Common scale, can be overridden
    } else if (subcategory === 'NENDOROID') {
      row['C:Scale'] = 'Non-Scale';
    } else if (subcategory === 'FIGMA') {
      row['C:Scale'] = 'Non-Scale';
    } else {
      row['C:Scale'] = 'See description';
    }

    // Material - typically PVC for Japanese figures
    row['C:Material'] = 'PVC';
  }

  return row;
}

/**
 * Convert object to CSV line with proper escaping
 */
function objectToCSVLine(obj: any, headers: string[]): string {
  return headers
    .map((header) => {
      const value = obj[header] || '';
      const stringValue = String(value);
      // Escape quotes and wrap in quotes if contains comma, quote, or newline
      if (stringValue.includes(',') || stringValue.includes('"') || stringValue.includes('\n')) {
        return `"${stringValue.replace(/"/g, '""')}"`;
      }
      return stringValue;
    })
    .join(',');
}

/**
 * Export selected listings to eBay CSV format
 *
 * @param listingIds - Array of listing IDs to export
 * @param netMarginPercent - Desired net profit margin after eBay fees (default 25%)
 */
export async function exportToEBayCSV(
  listingIds: string[],
  netMarginPercent: number = 25
): Promise<{ success: boolean; csv?: string; filename?: string; error?: string }> {
  try {
    if (!listingIds || listingIds.length === 0) {
      return {
        success: false,
        error: 'No listings selected for export',
      };
    }

    const db = await getDatabase();
    const collection = db.collection<MarketListing>('market_listings');

    // Fetch selected listings
    const listings = await collection
      .find({ _id: { $in: listingIds } })
      .toArray();

    if (listings.length === 0) {
      return {
        success: false,
        error: 'No listings found with the provided IDs',
      };
    }

    // Convert to eBay CSV rows with specified margin
    const csvRows = listings.map((listing) => listingToEBayRow(listing, netMarginPercent));

    // Define CSV headers (eBay File Exchange format)
    // Includes all possible fields for all niches - eBay ignores unused fields
    const headers = [
      '*Action(SiteID=US|Country=US|Currency=USD|Version=1193)',
      '*Category',
      '*Title',
      '*StartPrice',
      '*Quantity',
      '*Format',
      '*Duration',
      '*Location',
      '*Description',
      'C:Brand',
      'Product:UPC',
      'Product:ISBN',
      'PicURL',
      'ConditionID',
      'C:Model',
      'C:Type',
      // Luxury item fields
      'C:Exterior Color',
      'C:Exterior Material',
      'C:Department',
      'C:Style',
      'Color',
      // Videogame console fields
      'C:Platform',
      // Watch fields
      'C:Band Material',
      'C:Case Material',
      'C:Movement',
      'C:Dial Color',
      // Camera gear fields
      'C:Series',
      'C:Megapixels',
      'C:Optical Zoom',
      // Pokemon card fields
      'C:Card Name',
      'C:Card Number',
      'C:Set',
      'C:Rarity',
      'C:Language',
      // Stationary fields
      'C:Ink Color',
      'C:Point Size',
      'C:Features',
      // Collection Figures fields
      'C:Character',
      'C:Character Family',
      'C:Scale',
      'C:Material',
      // Shipping and returns
      '*ShippingType',
      'ShippingService-1:Option',
      'ShippingService-1:Cost',
      'DispatchTimeMax',
      'ReturnsAcceptedOption',
      'ReturnsWithinOption',
      'RefundOption',
      'ShippingCostPaidByOption',
    ];

    // Generate CSV content
    const csvLines = [
      headers.join(','), // Header row
      ...csvRows.map((row) => objectToCSVLine(row, headers)),
    ];

    const csv = csvLines.join('\n');

    // Generate filename with full timestamp
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').split('.')[0];
    const filename = `ebay-listings-${timestamp}.csv`;

    return {
      success: true,
      csv,
      filename,
    };
  } catch (error) {
    console.error('Error exporting listings to eBay CSV:', error);
    return {
      success: false,
      error: 'Failed to export listings',
    };
  }
}
