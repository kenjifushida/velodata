/**
 * Server Actions for CSV Export
 *
 * Handles exporting market listings to eBay and Shopify CSV formats.
 * - eBay: File Exchange CSV format
 * - Shopify: Product CSV import format
 *
 * References:
 * - eBay: https://www.ebay.com/help/selling/listings/creating-managing-listings/add-edit-items-file-exchange
 * - Shopify: https://help.shopify.com/en/manual/products/import-export/using-csv
 */
'use server';

import { getDatabase } from '@/lib/mongodb';
import type { MarketListing } from '@/lib/models/market-listing';
import { TCG_GAME_NAMES, GRADING_COMPANY_NAMES, NICHE_DISPLAY_NAMES } from '@/lib/constants';
import type { TCGGame, GradingCompany, NicheType } from '@/lib/models/market-listing';

/**
 * eBay File Exchange CSV fields
 * Required fields marked with *
 */
interface EBayCSVRow {
  // Required fields
  '*Action(SiteID=US|Country=JP|Currency=USD|Version=1193)': string;
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

  // TCG Card specifics (category-dependent)
  'C:Game'?: string;  // Required for TCG categories (183454, 183444, 38292)
  'C:Card Name'?: string;  // For TCG cards (183454)
  'C:Card Number'?: string;  // For TCG cards (183454)
  'C:Set'?: string;  // For TCG cards (183454)
  'C:Rarity'?: string;  // For TCG cards (183454)
  'C:Language'?: string;  // For TCG cards (183454)
  'CD:Professional Grader - (ID: 27501)'?: string;  // Required when ConditionID=2750
  'CD:Grade - (ID: 27502)'?: string;  // Required when ConditionID=2750
  'CDA:Certification Number - (ID: 27503)'?: string;  // Optional cert number for graded cards
  'CD:Card Condition - (ID: 40001)'?: string;  // Required when ConditionID=4000 (ungraded TCG)

  // Stationary specifics (category-dependent)
  'C:Ink Color'?: string;  // For pens (61778-61782)
  'C:Point Size'?: string;  // For pens (61778-61782)
  'C:Features'?: string;  // For stationary (61778-61782)

  // Collection Figures specifics (category-dependent)
  'C:Character'?: string;  // For action figures (261068)
  'C:Character Family'?: string;  // For action figures (261068)
  'C:Scale'?: string;  // For action figures (261068)
  'C:Material'?: string;  // For action figures (261068) and drinkware (46579)

  // Drinkware specifics (category-dependent)
  'C:Capacity'?: string;  // For mugs/cups (46579)
  'C:Theme'?: string;  // For mugs/cups (46579) - series/collection name
  'C:Country/Region of Manufacture'?: string;  // For mugs/cups (46579)
  'C:Region of Origin'?: string;  // For regional exclusives (46579)

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
  DRINKWARE: '46579', // Collectibles > Kitchen & Home > Mugs, Cups & Steins
};

/**
 * eBay category mapping for TCG games
 */
const TCG_GAME_CATEGORIES: Record<string, string> = {
  POKEMON: '183454', // CCG Individual Cards
  YUGIOH: '183454', // CCG Individual Cards (same as Pokemon)
  ONE_PIECE: '183454', // CCG Individual Cards (same as Pokemon)
  MAGIC: '183454', // CCG Individual Cards (same as Pokemon)
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
 * eBay Condition Descriptor Value IDs for Professional Grader (27501)
 * Maps grading company codes to eBay descriptor value IDs
 * Reference: https://developer.ebay.com/api-docs/user-guides/static/mip-user-guide/mip-enum-condition-descriptor-ids-for-trading-cards.html
 */
const EBAY_GRADER_VALUE_IDS: Record<string, string> = {
  PSA: '275010',
  BCCG: '275011',
  BVG: '275012',
  BGS: '275013',
  CSG: '275014',
  CGC: '275015',
  SGC: '275016',
  KSA: '275017',
  GMA: '275018',
  HGA: '275019',
};

/**
 * eBay Condition Descriptor Value IDs for Grade (27502)
 * Maps numeric grades to eBay descriptor value IDs
 */
const EBAY_GRADE_VALUE_IDS: Record<string, string> = {
  '10': '275020',
  '9.5': '275021',
  '9': '275022',
  '8.5': '275023',
  '8': '275024',
  '7.5': '275025',
  '7': '275026',
  '6.5': '275027',
  '6': '275028',
  '5.5': '275029',
  '5': '2750210',
  '4.5': '2750211',
  '4': '2750212',
  '3.5': '2750213',
  '3': '2750214',
  '2.5': '2750215',
  '2': '2750216',
  '1.5': '2750217',
  '1': '2750218',
};

/**
 * eBay Condition Descriptor Value IDs for ungraded Card Condition (40001)
 *
 * IMPORTANT: Categories 183454, 183444, 38292 (Collectible Card Games) use:
 *   400010 = Near Mint or Better
 *   400015 = Lightly Played (Excellent)
 *   400016 = Moderately Played (Very Good)
 *   400017 = Heavily Played (Poor)
 *
 * Categories 183050, 261328 (Sports/Non-Sports Trading Cards) use:
 *   400010 = Near Mint or Better
 *   400011 = Excellent
 *   400012 = Very Good
 *   400013 = Poor
 *
 * Reference: https://developer.ebay.com/api-docs/user-guides/static/mip-user-guide/mip-enum-condition-descriptor-ids-for-trading-cards.html
 */
const EBAY_CCG_CARD_CONDITION_VALUE_IDS: Record<string, string> = {
  N: '400010',   // Near Mint or Better
  S: '400010',   // Near Mint or Better
  A: '400015',   // Lightly Played (Excellent)
  B: '400016',   // Moderately Played (Very Good)
  C: '400017',   // Heavily Played (Poor)
  D: '400017',   // Heavily Played (Poor)
  JUNK: '400017', // Heavily Played (Poor)
};

/**
 * eBay Game item specific values for TCG categories
 * These must match eBay's accepted values exactly
 */
const EBAY_TCG_GAME_NAMES: Record<string, string> = {
  POKEMON: 'Pokémon TCG',
  YUGIOH: 'Yu-Gi-Oh! TCG',
  ONE_PIECE: 'One Piece Card Game',
  MAGIC: 'Magic: The Gathering',
  WEISS_SCHWARZ: 'Weiss Schwarz',
  DRAGON_BALL: 'Dragon Ball Super Card Game',
  DIGIMON: 'Digimon',
  VANGUARD: 'Cardfight!! Vanguard',
  UNION_ARENA: 'Union Arena',
  DUEL_MASTERS: 'Duel Masters',
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
  // Used by: VIDEOGAME, STATIONARY, COLLECTION_FIGURES, DRINKWARE
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
  DRINKWARE: 'RESTRICTED',
};

/**
 * Map condition rank to eBay condition ID
 *
 * @param rank - Condition rank from Hard-Off (N, S, A, B, C, D, JUNK)
 * @param nicheType - Product niche type
 * @param isGraded - Whether the item is professionally graded (PSA, BGS, etc.)
 * @returns eBay condition ID
 */
function mapToEBayCondition(rank?: string, nicheType?: string, isGraded?: boolean): string {
  // Graded cards use ConditionID 2750 (Graded - Certified)
  if (isGraded) {
    return '2750';
  }

  // TCG categories (183454, etc.) only accept 4000 for ungraded cards
  if (nicheType === 'TCG') {
    return '4000';
  }

  const strategy = nicheType ? NICHE_CONDITION_STRATEGY[nicheType] : 'STANDARD';
  const conditionMap = CONDITION_MAPPINGS[strategy] || CONDITION_MAPPINGS.STANDARD;

  return rank ? (conditionMap[rank] || '3000') : '3000';
}

/**
 * Map condition rank to TCG card condition text (matching eBay CCG descriptor labels)
 */
function mapTCGConditionToText(rank?: string, isGraded?: boolean, gradingCompany?: string, grade?: number): string {
  if (isGraded) {
    const company = gradingCompany || 'PSA';
    const gradeStr = grade ? String(grade) : '';
    return `Graded - ${company} ${gradeStr}`.trim();
  }

  const conditionMap: Record<string, string> = {
    N: 'Near Mint or Better',
    S: 'Near Mint or Better',
    A: 'Lightly Played (Excellent)',
    B: 'Moderately Played (Very Good)',
    C: 'Heavily Played (Poor)',
    D: 'Heavily Played (Poor)',
    JUNK: 'Heavily Played (Poor)',
  };

  return rank ? (conditionMap[rank] || 'Near Mint or Better') : 'Near Mint or Better';
}

/**
 * Generate eBay-compliant product description
 */
function generateEBayDescription(listing: MarketListing): string {
  const { attributes, niche_type } = listing;

  const nicheDescriptions: Record<string, string> = {
    WATCH: 'Authentic Pre-Owned Luxury Watch',
    CAMERA_GEAR: 'Professional Camera Equipment',
    TCG: 'Authentic Trading Card Game Card',
    LUXURY_ITEM: 'Authentic Designer Luxury Item',
    VIDEOGAME: 'Authentic Game Console from Japan',
    STATIONARY: 'Authentic Writing Instrument from Japan',
    COLLECTION_FIGURES: 'Authentic Collectible Figure from Japan',
    DRINKWARE: 'Authentic Japan-Limited Drinkware',
  };

  const title = nicheDescriptions[niche_type] || 'Authentic Pre-Owned Item';

  // Use TCG-specific condition text for card listings
  const conditionText = niche_type === 'TCG'
    ? mapTCGConditionToText(attributes.condition_rank, attributes.is_graded, attributes.grading_company, attributes.grade)
    : mapConditionToText(attributes.condition_rank);

  // eBay allows HTML in descriptions
  const description = `
<div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
  <h2>${title}</h2>

  <p><strong>Sourced and Shipped from Japan</strong></p>

  <h3>Item Details</h3>
  <ul>
    <li><strong>Condition:</strong> ${conditionText}</li>
  </ul>

  <h3>Shipping & Packaging</h3>
  <p>All items are carefully inspected, authenticated, and securely packaged with bubble wrap and
  protective materials to ensure safe international delivery.</p>

  <h3>Return Policy</h3>
  <p><strong>Returns are only accepted if you have an unboxing video.</strong> To be eligible for a return,
  you must record a continuous, unedited video of yourself opening the package from the moment it is received.
  No video = no return. This protects both parties.</p>

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
  DRINKWARE: 46.9, // Mugs/tumblers are bulky — similar shipping cost to figures
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
 * Get the best title for export (prefer English translation if available)
 *
 * @param listing - Market listing
 * @returns English title if available, otherwise original Japanese title
 */
function getExportTitle(listing: MarketListing): string {
  const { attributes } = listing;
  // Use English translation if available, otherwise fall back to original title
  return attributes.title_en || listing.title;
}

/**
 * Convert market listing to eBay CSV row
 *
 * @param listing - Market listing to convert
 * @param netMarginPercent - Desired net profit margin after fees (default 25%)
 */
function listingToEBayRow(listing: MarketListing, netMarginPercent: number = 25, handlingTime: number = 1): EBayCSVRow {
  const { attributes } = listing;

  // Get title (prefer English translation)
  const title = getExportTitle(listing);

  // Convert JPY to USD
  const costUSD = listing.price_jpy * JPY_TO_USD_RATE;

  // Get niche-specific shipping cost
  const shippingCost = getShippingCost(listing.niche_type);

  // Calculate sale price with desired net margin
  const priceUSD = Math.round(calculateSalePriceWithMargin(costUSD, netMarginPercent, shippingCost)).toFixed(2);

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
    '*Action(SiteID=US|Country=JP|Currency=USD|Version=1193)': 'Add',
    '*Category': ebayCategory,
    '*Title': title.substring(0, 80), // eBay title limit is 80 characters (uses English if available)
    '*StartPrice': priceUSD,
    '*Quantity': '1',
    '*Format': 'FixedPrice',
    '*Duration': 'GTC', // Good 'Til Cancelled
    '*Location': 'Tokyo',
    '*Description': generateEBayDescription(listing),

    // Product identifiers
    'C:Brand': attributes.brand || 'Unbranded',
    'Product:UPC': 'Does not apply',
    'Product:ISBN': 'Does not apply',

    // Images (eBay supports up to 12 images, pipe-separated)
    'PicURL': listing.image_urls.slice(0, 12).join('|'),

    // Item specifics
    'ConditionID': mapToEBayCondition(attributes.condition_rank, listing.niche_type, attributes.is_graded),
    'C:Model': attributes.model || attributes.model_number || attributes.reference_number || 'See description',
    'C:Type': attributes.subcategory || listing.niche_type,

    // Shipping
    '*ShippingType': 'Flat',
    'ShippingService-1:Option': 'ShippingMethodStandard',
    'ShippingService-1:Cost': '0.00', // Free shipping (cost included in item price)
    'DispatchTimeMax': String(handlingTime),

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
    // Item specifics: Game (required), Card Name, Card Number, Set, Rarity, Language
    row['C:Game'] = attributes.tcg_game
      ? EBAY_TCG_GAME_NAMES[attributes.tcg_game] || 'Trading Card Game'
      : 'Trading Card Game';
    row['C:Card Name'] = listing.title.substring(0, 50);
    row['C:Card Number'] = attributes.card_number || 'See description';
    row['C:Set'] = attributes.set_code || attributes.set || 'See description';
    row['C:Rarity'] = attributes.rarity || 'See description';
    row['C:Language'] = attributes.language || 'JP'; // Default for Japanese marketplace

    // Condition descriptor fields
    if (!attributes.is_graded) {
      // Ungraded: Card Condition descriptor (required when ConditionID=4000)
      const condRank = attributes.condition_rank || 'A';
      row['CD:Card Condition - (ID: 40001)'] = EBAY_CCG_CARD_CONDITION_VALUE_IDS[condRank] || '400010';
    }
    if (attributes.is_graded) {
      const graderCode = attributes.grading_company || 'PSA';
      row['CD:Professional Grader - (ID: 27501)'] = EBAY_GRADER_VALUE_IDS[graderCode] || EBAY_GRADER_VALUE_IDS['PSA'];
      row['CD:Grade - (ID: 27502)'] = attributes.grade
        ? EBAY_GRADE_VALUE_IDS[String(attributes.grade)] || String(attributes.grade)
        : '';
      if (attributes.cert_number) {
        row['CDA:Certification Number - (ID: 27503)'] = attributes.cert_number;
      }
    }
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
  } else if (listing.niche_type === 'DRINKWARE') {
    // Drinkware item specifics - Category 46579 (Mugs, Cups & Steins)
    const brand = attributes.brand || '';
    const itemType = attributes.item_type || '';
    const material = attributes.material || '';
    const capacityMl = attributes.capacity_ml;
    const series = attributes.series || '';
    const region = attributes.region || '';

    if (brand) {
      row['C:Brand'] = brand;
    }

    // Type of drinkware (Mug, Tumbler, Thermos, etc.)
    const itemTypeMap: Record<string, string> = {
      MUG: 'Mug',
      TUMBLER: 'Tumbler',
      THERMOS: 'Thermos/Vacuum Bottle',
      CUP: 'Cup',
      BOTTLE: 'Water Bottle',
      STRAW: 'Straw',
    };
    row['C:Type'] = itemTypeMap[itemType] || 'See description';

    if (material) {
      row['C:Material'] = material;
    }

    // Capacity in fluid ounces (eBay uses oz for US buyers)
    if (capacityMl) {
      const capacityOz = Math.round(Number(capacityMl) * 0.033814 * 10) / 10;
      row['C:Capacity'] = `${capacityOz} fl oz`;
    }

    // Series/collection name is a key differentiator for Japan-limited items
    if (series) {
      row['C:Theme'] = series;
    }

    // Country of manufacture and regional exclusivity
    row['C:Country/Region of Manufacture'] = 'Japan';
    if (region && region.toLowerCase() !== 'japan') {
      row['C:Region of Origin'] = region;
    }
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
  netMarginPercent: number = 25,
  handlingTime: number = 1
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
    const csvRows = listings.map((listing) => listingToEBayRow(listing, netMarginPercent, handlingTime));

    // Define CSV headers (eBay File Exchange format)
    // Includes all possible fields for all niches - eBay ignores unused fields
    const headers = [
      '*Action(SiteID=US|Country=JP|Currency=USD|Version=1193)',
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
      // TCG card fields
      'C:Game',
      'C:Card Name',
      'C:Card Number',
      'C:Set',
      'C:Rarity',
      'C:Language',
      'CD:Card Condition - (ID: 40001)',
      'CD:Professional Grader - (ID: 27501)',
      'CD:Grade - (ID: 27502)',
      'CDA:Certification Number - (ID: 27503)',
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

// ============================================================================
// SHOPIFY EXPORT
// ============================================================================

/**
 * Shopify Product CSV fields
 * Based on https://help.shopify.com/en/manual/products/import-export/using-csv
 */
interface ShopifyCSVRow {
  // Required fields
  Handle: string;
  Title: string;

  // Product details
  'Body (HTML)': string;
  Vendor: string;
  'Product Category': string;
  Type: string;
  Tags: string;
  Published: string;

  // Variant details
  'Option1 Name': string;
  'Option1 Value': string;
  'Variant SKU': string;
  'Variant Grams': string;
  'Variant Inventory Tracker': string;
  'Variant Inventory Qty': string;
  'Variant Inventory Policy': string;
  'Variant Fulfillment Service': string;
  'Variant Price': string;
  'Variant Compare At Price': string;
  'Variant Requires Shipping': string;
  'Variant Taxable': string;
  'Variant Barcode': string;
  'Variant Weight Unit': string;

  // Images
  'Image Src': string;
  'Image Position': string;
  'Image Alt Text': string;

  // SEO
  'SEO Title': string;
  'SEO Description': string;

  // Status
  Status: string;

  // Collection (for organizing products into Shopify collections)
  Collection: string;

  // Cost tracking (for inventory management)
  'Cost per item': string;
}

/**
 * Shopify product categories for TCG
 */
const SHOPIFY_TCG_CATEGORIES: Record<string, string> = {
  POKEMON: 'Collectible Trading Cards',
  YUGIOH: 'Collectible Trading Cards',
  ONE_PIECE: 'Collectible Trading Cards',
  MAGIC: 'Collectible Trading Cards',
  WEISS_SCHWARZ: 'Collectible Trading Cards',
  DRAGON_BALL: 'Collectible Trading Cards',
  DIGIMON: 'Collectible Trading Cards',
  VANGUARD: 'Collectible Trading Cards',
  UNION_ARENA: 'Collectible Trading Cards',
  DUEL_MASTERS: 'Collectible Trading Cards',
};

/**
 * Shopify Collection mapping for TCG games
 * Maps internal TCG game codes to Shopify collection names
 */
const SHOPIFY_TCG_COLLECTIONS: Record<string, string> = {
  POKEMON: 'Pokemon Card Game',
  YUGIOH: 'Yu-Gi-Oh!',
  ONE_PIECE: 'One Piece Card Game',
  MAGIC: 'Magic: The Gathering',
  UNION_ARENA: 'Union Arena',
  // Games without dedicated collections yet
  WEISS_SCHWARZ: '',
  DRAGON_BALL: '',
  DIGIMON: '',
  VANGUARD: '',
  DUEL_MASTERS: '',
  HOLOLIVE: 'hololive Official Card Game',
};

/**
 * Shopify product categories by niche
 */
const SHOPIFY_NICHE_CATEGORIES: Record<string, string> = {
  TCG: 'Collectible Trading Cards',
  WATCH: 'Apparel & Accessories > Jewelry > Watches',
  CAMERA_GEAR: 'Cameras & Optics > Camera & Optic Accessories',
  LUXURY_ITEM: 'Apparel & Accessories > Handbags, Wallets & Cases',
  VIDEOGAME: 'Electronics > Video Game Consoles',
  STATIONARY: 'Office Supplies > Writing Instruments',
  COLLECTION_FIGURES: 'Toys & Games > Toys > Action Figures',
  DRINKWARE: 'Home & Garden > Kitchen & Dining > Drinkware',
};

/**
 * Default weight in grams by niche (cards are ~100g with sleeve/toploader)
 */
const WEIGHT_BY_NICHE: Record<string, number> = {
  TCG: 100,
  WATCH: 300,
  CAMERA_GEAR: 500,
  LUXURY_ITEM: 400,
  VIDEOGAME: 800,
  STATIONARY: 100,
  COLLECTION_FIGURES: 500,
  DRINKWARE: 600, // Mugs/tumblers are heavier than figures
};

/**
 * Generate URL-safe handle from title
 */
function generateHandle(listing: MarketListing): string {
  const baseHandle = listing.title
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .substring(0, 50);

  // Add unique suffix from listing ID
  const idSuffix = listing._id.substring(listing._id.length - 6);
  return `${baseHandle}-${idSuffix}`;
}

/**
 * Generate Shopify-compliant product description with TCG focus
 */
function generateShopifyDescription(listing: MarketListing): string {
  const { attributes, niche_type } = listing;

  const nicheLabel = NICHE_DISPLAY_NAMES[niche_type as NicheType] || niche_type;

  let description = `<div style="font-family: system-ui, -apple-system, sans-serif;">`;
  description += `<h2>${listing.title}</h2>`;
  description += `<p><strong>Authentic ${nicheLabel} from Japan</strong></p>`;

  // TCG-specific details
  if (niche_type === 'TCG') {
    description += `<h3>Card Details</h3><ul>`;

    if (attributes.tcg_game) {
      const gameName = TCG_GAME_NAMES[attributes.tcg_game as TCGGame] || attributes.tcg_game;
      description += `<li><strong>Game:</strong> ${gameName}</li>`;
    }

    if (attributes.set_code) {
      description += `<li><strong>Set:</strong> ${attributes.set_code}</li>`;
    }

    if (attributes.card_number) {
      description += `<li><strong>Card Number:</strong> ${attributes.card_number}</li>`;
    }

    if (attributes.rarity) {
      description += `<li><strong>Rarity:</strong> ${attributes.rarity}</li>`;
    }

    if (attributes.language) {
      description += `<li><strong>Language:</strong> ${attributes.language}</li>`;
    }

    // Grading information
    if (attributes.is_graded) {
      if (attributes.grading_company) {
        const companyName = GRADING_COMPANY_NAMES[attributes.grading_company as GradingCompany] || attributes.grading_company;
        description += `<li><strong>Grading Company:</strong> ${companyName}</li>`;
      }
      if (attributes.grade) {
        description += `<li><strong>Grade:</strong> ${attributes.grade}${attributes.grade_qualifier ? ` (${attributes.grade_qualifier})` : ''}</li>`;
      }
      if (attributes.cert_number) {
        description += `<li><strong>Cert Number:</strong> ${attributes.cert_number}</li>`;
      }
    }

    description += `</ul>`;
  }

  // Condition - use TCG-specific terminology for card listings
  if (niche_type === 'TCG') {
    description += `<h3>Condition</h3>`;
    description += `<p>${mapTCGConditionToText(attributes.condition_rank, attributes.is_graded, attributes.grading_company, attributes.grade)}</p>`;
  } else if (attributes.condition_rank) {
    description += `<h3>Condition</h3>`;
    description += `<p>${mapConditionToText(attributes.condition_rank)}</p>`;
  }

  // Shipping info
  description += `<h3>Shipping</h3>`;
  description += `<p>Ships from Japan with tracking. Items are carefully packaged with protective materials.</p>`;

  description += `<p><em>All items are sold as-is. Please review photos carefully before purchase.</em></p>`;
  description += `</div>`;

  return description;
}

/**
 * Generate tags for Shopify product
 *
 * @param listing - Market listing
 */
function generateShopifyTags(listing: MarketListing): string {
  const tags: string[] = [];
  const { attributes, niche_type } = listing;

  // Niche tag
  tags.push(niche_type);

  // TCG-specific tags
  if (niche_type === 'TCG') {
    if (attributes.tcg_game) {
      const gameName = TCG_GAME_NAMES[attributes.tcg_game as TCGGame] || attributes.tcg_game;
      tags.push(gameName.replace(/[^a-zA-Z0-9\s]/g, ''));
    }

    if (attributes.is_graded) {
      tags.push('Graded');
      if (attributes.grading_company) {
        tags.push(attributes.grading_company);
      }
      if (attributes.grade) {
        tags.push(`Grade ${attributes.grade}`);
      }
    } else {
      tags.push('Raw');
    }

    if (attributes.set_code) {
      tags.push(attributes.set_code);
    }

    if (attributes.rarity) {
      tags.push(attributes.rarity);
    }

    if (attributes.language) {
      tags.push(attributes.language);
    }
  }

  // Brand tag
  if (attributes.brand) {
    tags.push(attributes.brand);
  }

  // Condition tag
  if (attributes.condition_rank) {
    tags.push(`Condition-${attributes.condition_rank}`);
  }

  // Japan origin tag
  tags.push('Japan', 'Japanese Import');

  return tags.join(', ');
}

/**
 * Calculate Shopify sale price with desired margin
 *
 * For Shopify, shipping is separate from product price.
 * The product price covers: item cost + margin + payment fees
 * Net margin is calculated on the item sale only.
 */
function calculateShopifyPrice(
  costJPY: number,
  desiredMarginPercent: number
): number {
  const SHOPIFY_PAYMENT_FEE_PERCENT = 0.029;
  const SHOPIFY_PAYMENT_FEE_FIXED = 0.30;

  const costUSD = costJPY * JPY_TO_USD_RATE;
  const desiredProfit = costUSD * (desiredMarginPercent / 100);

  // Product price only - shipping is charged separately
  const salePrice =
    (costUSD + desiredProfit + SHOPIFY_PAYMENT_FEE_FIXED) /
    (1 - SHOPIFY_PAYMENT_FEE_PERCENT);

  return salePrice;
}

/**
 * Convert market listing to Shopify CSV row
 *
 * @param listing - Market listing to convert
 * @param netMarginPercent - Desired net profit margin (default 25%)
 */
function listingToShopifyRow(
  listing: MarketListing,
  netMarginPercent: number = 25
): ShopifyCSVRow {
  const { attributes, niche_type } = listing;

  // Get title (prefer English translation)
  const title = getExportTitle(listing);

  // Calculate sale price (shipping is separate)
  const priceUSD = calculateShopifyPrice(listing.price_jpy, netMarginPercent);

  // Get product category
  let category: string;
  if (niche_type === 'TCG' && attributes.tcg_game) {
    category = SHOPIFY_TCG_CATEGORIES[attributes.tcg_game] || SHOPIFY_NICHE_CATEGORIES.TCG;
  } else {
    category = SHOPIFY_NICHE_CATEGORIES[niche_type] || 'Miscellaneous';
  }

  // Get weight
  const weightGrams = WEIGHT_BY_NICHE[niche_type] || 100;

  // Generate SKU
  const sku = `VD-${listing._id.substring(0, 12).toUpperCase()}`;

  // Get vendor/brand
  const vendor = attributes.brand || 'VeloData Japan';

  // Get product type
  let productType: string;
  if (niche_type === 'TCG') {
    const gameName = attributes.tcg_game
      ? TCG_GAME_NAMES[attributes.tcg_game as TCGGame] || attributes.tcg_game
      : 'Trading';
    productType = attributes.is_graded ? `Graded ${gameName} Card` : `${gameName} Card`;
  } else {
    productType = NICHE_DISPLAY_NAMES[niche_type as NicheType] || niche_type;
  }

  // Get collection for TCG items
  let collection = '';
  if (niche_type === 'TCG' && attributes.tcg_game) {
    collection = SHOPIFY_TCG_COLLECTIONS[attributes.tcg_game] || '';
  }

  const row: ShopifyCSVRow = {
    Handle: generateHandle(listing),
    Title: title.substring(0, 255), // Uses English title if available
    'Body (HTML)': generateShopifyDescription(listing),
    Vendor: vendor,
    'Product Category': category,
    Type: productType,
    Tags: generateShopifyTags(listing),
    Published: 'true',

    'Option1 Name': 'Title',
    'Option1 Value': 'Default Title',
    'Variant SKU': sku,
    'Variant Grams': String(weightGrams),
    'Variant Inventory Tracker': 'shopify',
    'Variant Inventory Qty': '1',
    'Variant Inventory Policy': 'deny',
    'Variant Fulfillment Service': 'manual',
    'Variant Price': Math.round(priceUSD).toFixed(2),
    'Variant Compare At Price': '',
    'Variant Requires Shipping': 'true',
    'Variant Taxable': 'true',
    'Variant Barcode': '',
    'Variant Weight Unit': 'g',

    'Image Src': listing.image_urls[0] || '',
    'Image Position': '1',
    'Image Alt Text': title.substring(0, 125), // Uses English title if available

    'SEO Title': title.substring(0, 70), // Uses English title if available
    'SEO Description': `${title.substring(0, 150)} - Authentic from Japan`, // Uses English title if available

    Status: 'active',

    // Collection for organizing products (TCG games mapped to Shopify collections)
    Collection: collection,

    // Cost per item for inventory tracking (item cost in USD)
    'Cost per item': (listing.price_jpy * JPY_TO_USD_RATE).toFixed(2),
  };

  return row;
}

/**
 * Export selected listings to Shopify CSV format
 *
 * @param listingIds - Array of listing IDs to export
 * @param netMarginPercent - Desired net profit margin (default 25%)
 */
export async function exportToShopifyCSV(
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

    // Convert to Shopify CSV rows
    const csvRows = listings.map((listing) => listingToShopifyRow(listing, netMarginPercent));

    // For listings with multiple images, we need additional rows
    const allRows: ShopifyCSVRow[] = [];

    for (let i = 0; i < listings.length; i++) {
      const listing = listings[i];
      const baseRow = csvRows[i];

      // Add the main row
      allRows.push(baseRow);

      // Add additional image rows (Shopify supports up to 250 images)
      // Skip the first image as it's already in the main row
      for (let imgIndex = 1; imgIndex < Math.min(listing.image_urls.length, 10); imgIndex++) {
        const imageRow: ShopifyCSVRow = {
          Handle: baseRow.Handle,
          Title: '',
          'Body (HTML)': '',
          Vendor: '',
          'Product Category': '',
          Type: '',
          Tags: '',
          Published: '',
          'Option1 Name': '',
          'Option1 Value': '',
          'Variant SKU': '',
          'Variant Grams': '',
          'Variant Inventory Tracker': '',
          'Variant Inventory Qty': '',
          'Variant Inventory Policy': '',
          'Variant Fulfillment Service': '',
          'Variant Price': '',
          'Variant Compare At Price': '',
          'Variant Requires Shipping': '',
          'Variant Taxable': '',
          'Variant Barcode': '',
          'Variant Weight Unit': '',
          'Image Src': listing.image_urls[imgIndex],
          'Image Position': String(imgIndex + 1),
          'Image Alt Text': `${listing.title.substring(0, 100)} - Image ${imgIndex + 1}`,
          'SEO Title': '',
          'SEO Description': '',
          Status: '',
          Collection: '',
          'Cost per item': '',
        };
        allRows.push(imageRow);
      }
    }

    // Define CSV headers
    const headers: (keyof ShopifyCSVRow)[] = [
      'Handle',
      'Title',
      'Body (HTML)',
      'Vendor',
      'Product Category',
      'Type',
      'Tags',
      'Published',
      'Option1 Name',
      'Option1 Value',
      'Variant SKU',
      'Variant Grams',
      'Variant Inventory Tracker',
      'Variant Inventory Qty',
      'Variant Inventory Policy',
      'Variant Fulfillment Service',
      'Variant Price',
      'Variant Compare At Price',
      'Variant Requires Shipping',
      'Variant Taxable',
      'Variant Barcode',
      'Variant Weight Unit',
      'Image Src',
      'Image Position',
      'Image Alt Text',
      'SEO Title',
      'SEO Description',
      'Status',
      'Collection',
      'Cost per item',
    ];

    // Generate CSV content
    const csvLines = [
      headers.join(','),
      ...allRows.map((row) => objectToCSVLine(row, headers)),
    ];

    const csv = csvLines.join('\n');

    // Generate filename
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').split('.')[0];
    const filename = `shopify-products-${timestamp}.csv`;

    return {
      success: true,
      csv,
      filename,
    };
  } catch (error) {
    console.error('Error exporting listings to Shopify CSV:', error);
    return {
      success: false,
      error: 'Failed to export listings',
    };
  }
}
