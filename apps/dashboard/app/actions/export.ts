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
  'C:Condition': string;
  'C:Model': string;
  'C:Type': string;

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
};

/**
 * Map condition rank to eBay condition ID
 */
function mapToEBayCondition(rank?: string): string {
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
 * Convert market listing to eBay CSV row
 */
function listingToEBayRow(listing: MarketListing): EBayCSVRow {
  const { attributes } = listing;

  // Convert JPY to USD (approximate exchange rate - should be updated)
  const exchangeRate = 0.0067; // 1 JPY = 0.0067 USD
  const priceUSD = (listing.price_jpy * exchangeRate * 1.5).toFixed(2); // 50% markup

  const row: EBayCSVRow = {
    // Required fields
    '*Action(SiteID=US|Country=US|Currency=USD|Version=1193)': 'Add',
    '*Category': EBAY_CATEGORIES[listing.niche_type] || '15230',
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
    'C:Condition': mapToEBayCondition(attributes.condition_rank),
    'C:Model': attributes.model || attributes.model_number || attributes.reference_number || 'See description',
    'C:Type': attributes.subcategory || listing.niche_type,

    // Shipping
    '*ShippingType': 'Flat',
    'ShippingService-1:Option': 'USPSPriorityMailInternational',
    'ShippingService-1:Cost': '25.00', // International shipping from Japan
    'DispatchTimeMax': '5', // 5 business days to ship

    // Returns
    'ReturnsAcceptedOption': 'ReturnsAccepted',
    'ReturnsWithinOption': 'Days_30',
    'RefundOption': 'MoneyBack',
    'ShippingCostPaidByOption': 'Buyer',
  };

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
 */
export async function exportToEBayCSV(
  listingIds: string[]
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

    // Convert to eBay CSV rows
    const csvRows = listings.map(listingToEBayRow);

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
      'C:Condition',
      'C:Model',
      'C:Type',
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
