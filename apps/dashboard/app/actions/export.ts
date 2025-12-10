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

  // Images
  'PicURL': string;

  // Item specifics
  'ConditionID': string;
  'C:Model': string;
  'C:Type': string;

  // Luxury item specifics (required for category 169291 - Women's Bags & Handbags)
  'C:Exterior Color'?: string;
  'C:Exterior Material'?: string;
  'C:Department'?: string;
  'C:Style'?: string;

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
  POKEMON_CARD: '183454', // Pokemon Trading Card Game
  LUXURY_ITEM: '169291', // Women's Bags & Handbags (default)
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
 * Get eBay category for a luxury item based on subcategory
 */
function getLuxuryItemCategory(subcategory?: string): string {
  if (subcategory && LUXURY_SUBCATEGORY_CATEGORIES[subcategory]) {
    return LUXURY_SUBCATEGORY_CATEGORIES[subcategory];
  }
  return EBAY_CATEGORIES.LUXURY_ITEM; // Default to bags category
}

/**
 * Map condition rank to eBay condition ID
 *
 * @param rank - Condition rank from Hard-Off
 * @param nicheType - Product niche type (different categories may require different condition formats)
 */
function mapToEBayCondition(rank?: string, nicheType?: string): string {
  // For luxury items (Women's Bags & Handbags), use fashion category condition IDs
  if (nicheType === 'LUXURY_ITEM') {
    const luxuryConditionMap: Record<string, string> = {
      N: '1000', // New with tags
      S: '1500', // New without tags
      A: '3000', // Pre-owned - Excellent
      B: '4000', // Pre-owned - Very Good
      C: '5000', // Pre-owned - Good
      D: '6000', // Pre-owned - Fair
      JUNK: '7000', // For parts or not working
    };
    return rank ? (luxuryConditionMap[rank] || '3000') : '3000';
  }

  // For other categories, use standard condition IDs
  const conditionMap: Record<string, string> = {
    N: '1000', // New
    S: '1500', // New other (see details)
    A: '3000', // Used - Excellent
    B: '4000', // Used - Very Good
    C: '5000', // Used - Good
    D: '6000', // Used - Acceptable
    JUNK: '7000', // For parts or not working
  };

  return rank ? (conditionMap[rank] || '3000') : '3000';
}

/**
 * Generate eBay-compliant product description
 */
function generateEBayDescription(listing: MarketListing): string {
  const nicheDescriptions: Record<string, string> = {
    WATCH: 'Authentic Pre-Owned Luxury Watch from Japan',
    CAMERA_GEAR: 'Professional Camera Equipment from Japan',
    POKEMON_CARD: 'Authentic Pokemon Trading Card from Japan',
    LUXURY_ITEM: 'Authentic Designer Luxury Item from Japan',
  };

  const title = nicheDescriptions[listing.niche_type] || 'Authentic Product from Japan';

  // eBay allows HTML in descriptions
  const description = `
<div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
  <h2>${title}</h2>

  <p><strong>Shipped Direct from Japan</strong></p>

  <p>This is an original, authentic product sourced directly from a trusted Japanese marketplace.
  Japanese pre-owned items are renowned for their exceptional condition standards and quality.</p>

  <h3>Item Details</h3>
  <ul>
    <li><strong>Condition:</strong> ${mapConditionToText(listing.attributes.condition_rank)}</li>
    <li><strong>Source:</strong> ${listing.source.display_name}</li>
    <li><strong>Origin:</strong> Japan</li>
  </ul>

  <h3>Shipping & Packaging</h3>
  <p>All items are carefully inspected, authenticated, and securely packaged with bubble wrap and
  protective materials to ensure safe international delivery.</p>

  <h3>Condition Grading</h3>
  <p>Japanese marketplace condition grades are highly reliable. Items graded as "Excellent" or better
  show minimal signs of use.</p>

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
 * eBay fee structure
 */
const EBAY_FINAL_VALUE_FEE = 0.1325; // 13.25%
const EBAY_PAYMENT_PROCESSING_PERCENT = 0.0235; // 2.35%
const EBAY_PAYMENT_PROCESSING_FIXED = 0.30; // $0.30
const EBAY_INTERNATIONAL_FEE = 0.0165; // 1.65%
const SHIPPING_COST_USD = 30.0; // $30 FedEx International
const JPY_TO_USD_RATE = 0.0067; // Exchange rate

/**
 * Calculate sale price to achieve desired net margin after eBay fees
 *
 * @param costUSD - Item cost in USD
 * @param desiredMarginPercent - Desired net profit margin (e.g., 25 for 25%)
 * @returns Sale price that achieves the desired net margin
 */
function calculateSalePriceWithMargin(costUSD: number, desiredMarginPercent: number): number {
  const totalFeePercent =
    EBAY_FINAL_VALUE_FEE + EBAY_PAYMENT_PROCESSING_PERCENT + EBAY_INTERNATIONAL_FEE;

  const desiredProfit = costUSD * (desiredMarginPercent / 100);

  const salePrice =
    (costUSD + SHIPPING_COST_USD + desiredProfit + EBAY_PAYMENT_PROCESSING_FIXED) /
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

  // Calculate sale price with desired net margin
  const priceUSD = calculateSalePriceWithMargin(costUSD, netMarginPercent).toFixed(2);

  // Determine eBay category (use subcategory for luxury items)
  const ebayCategory = listing.niche_type === 'LUXURY_ITEM'
    ? getLuxuryItemCategory(attributes.subcategory)
    : (EBAY_CATEGORIES[listing.niche_type] || '15230');

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

    // Images
    'PicURL': listing.image_url || '',

    // Item specifics
    'ConditionID': mapToEBayCondition(attributes.condition_rank, listing.niche_type),
    'C:Model': attributes.model || attributes.model_number || attributes.reference_number || 'See description',
    'C:Type': attributes.subcategory || listing.niche_type,

    // Shipping
    '*ShippingType': 'Flat',
    'ShippingService-1:Option': 'ShippingMethodStandard',
    'ShippingService-1:Cost': '30.00', // International shipping from Japan (FedEx)
    'DispatchTimeMax': '5', // 5 business days to ship

    // Returns
    'ReturnsAcceptedOption': 'ReturnsAccepted',
    'ReturnsWithinOption': 'Days_30',
    'RefundOption': 'MoneyBack',
    'ShippingCostPaidByOption': 'Buyer',
  };

  // Add luxury item specifics if applicable (required for Women's Bags & Handbags category)
  if (listing.niche_type === 'LUXURY_ITEM') {
    row['C:Exterior Color'] = 'Multicolor'; // Safe default, can be edited later
    row['C:Exterior Material'] = determineExteriorMaterial(attributes.brand, listing.title);
    row['C:Department'] = 'Women'; // Most luxury items in this category are women's
    row['C:Style'] = mapSubcategoryToStyle(attributes.subcategory);
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
      'C:Exterior Color',
      'C:Exterior Material',
      'C:Department',
      'C:Style',
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

    // Generate filename with timestamp
    const timestamp = new Date().toISOString().split('T')[0];
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
