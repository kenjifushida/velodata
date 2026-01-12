/**
 * Server Actions for Market Listings
 *
 * Handles fetching, filtering, and searching market listings from MongoDB.
 */
'use server';

import { getDatabase } from '@/lib/mongodb';
import type {
  MarketListing,
  MarketListingFilters,
  MarketListingsResponse,
  NicheType,
  SourceId,
} from '@/lib/models/market-listing';

/**
 * Fetch market listings with filters and pagination
 */
export async function getMarketListings(
  filters: MarketListingFilters = {}
): Promise<MarketListingsResponse> {
  try {
    const db = await getDatabase();
    const collection = db.collection<MarketListing>('market_listings');

    const {
      niche_type,
      source_id,
      min_price,
      max_price,
      search,
      is_processed,
      page = 1,
      limit = 20,
    } = filters;

    // Build MongoDB query
    const query: any = {};

    if (niche_type) {
      query.niche_type = niche_type;
    }

    if (source_id) {
      query['source.source_id'] = source_id;
    }

    if (min_price !== undefined || max_price !== undefined) {
      query.price_jpy = {};
      if (min_price !== undefined) {
        query.price_jpy.$gte = min_price;
      }
      if (max_price !== undefined) {
        query.price_jpy.$lte = max_price;
      }
    }

    if (search) {
      // Text search on title field
      query.$or = [
        { title: { $regex: search, $options: 'i' } },
        { 'attributes.brand': { $regex: search, $options: 'i' } },
      ];
    }

    if (is_processed !== undefined) {
      query.is_processed = is_processed;
    }

    // Calculate pagination
    const skip = (page - 1) * limit;

    // Execute query with pagination
    const [listings, total] = await Promise.all([
      collection
        .find(query)
        .sort({ created_at: -1 })
        .skip(skip)
        .limit(limit)
        .toArray(),
      collection.countDocuments(query),
    ]);

    const totalPages = Math.ceil(total / limit);

    return {
      listings: listings as MarketListing[],
      total,
      page,
      limit,
      totalPages,
    };
  } catch (error) {
    console.error('Error fetching market listings:', error);
    throw new Error('Failed to fetch market listings');
  }
}

/**
 * Get available filter options (for dropdowns)
 */
export async function getFilterOptions(): Promise<{
  nicheTypes: NicheType[];
  sources: SourceId[];
  priceRange: { min_price: number; max_price: number };
}> {
  try {
    const db = await getDatabase();
    const collection = db.collection<MarketListing>('market_listings');

    // Get unique niche types
    const nicheTypes = await collection.distinct('niche_type') as NicheType[];

    // Get unique sources
    const sources = await collection.distinct('source.source_id') as SourceId[];

    // Get price range
    const priceStats = await collection
      .aggregate([
        {
          $group: {
            _id: null,
            min_price: { $min: '$price_jpy' },
            max_price: { $max: '$price_jpy' },
          },
        },
      ])
      .toArray();

    const priceRange = priceStats[0]
      ? { min_price: priceStats[0].min_price || 0, max_price: priceStats[0].max_price || 100000 }
      : { min_price: 0, max_price: 100000 };

    return {
      nicheTypes,
      sources,
      priceRange,
    };
  } catch (error) {
    console.error('Error fetching filter options:', error);
    return {
      nicheTypes: [],
      sources: [],
      priceRange: { min_price: 0, max_price: 100000 },
    };
  }
}

/**
 * Get statistics for dashboard summary
 */
export async function getListingStats() {
  try {
    const db = await getDatabase();
    const collection = db.collection<MarketListing>('market_listings');

    const [totalListings, processedListings, nicheBreakdown] = await Promise.all([
      collection.countDocuments(),
      collection.countDocuments({ is_processed: true }),
      collection
        .aggregate([
          {
            $group: {
              _id: '$niche_type',
              count: { $sum: 1 },
            },
          },
        ])
        .toArray(),
    ]);

    return {
      totalListings,
      processedListings,
      unprocessedListings: totalListings - processedListings,
      nicheBreakdown,
    };
  } catch (error) {
    console.error('Error fetching listing stats:', error);
    return {
      totalListings: 0,
      processedListings: 0,
      unprocessedListings: 0,
      nicheBreakdown: [],
    };
  }
}
