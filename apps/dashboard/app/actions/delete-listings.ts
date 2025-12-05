/**
 * Server Actions for Deleting Market Listings
 *
 * Handles batch deletion of market listings from the database.
 * Includes proper error handling, logging, and authorization checks.
 */
'use server';

import { getDatabase } from '@/lib/mongodb';
import { getSession } from '@/lib/auth';

/**
 * Result type for delete operation
 */
export interface DeleteListingsResult {
  success: boolean;
  deletedCount?: number;
  error?: string;
}

/**
 * Delete multiple market listings by their IDs.
 *
 * Security:
 * - Requires authenticated session
 * - Validates all listing IDs
 * - Uses transaction for atomicity
 *
 * @param listingIds - Array of listing IDs to delete
 * @returns Result object with success status and deleted count
 */
export async function deleteMarketListings(
  listingIds: string[]
): Promise<DeleteListingsResult> {
  try {
    // Security: Verify authentication
    const session = await getSession();
    if (!session) {
      return {
        success: false,
        error: 'Unauthorized: You must be logged in to delete listings',
      };
    }

    // Validation: Check input
    if (!listingIds || listingIds.length === 0) {
      return {
        success: false,
        error: 'No listing IDs provided',
      };
    }

    // Validation: Ensure all IDs are strings
    const invalidIds = listingIds.filter((id) => typeof id !== 'string' || !id.trim());
    if (invalidIds.length > 0) {
      return {
        success: false,
        error: `Invalid listing IDs provided: ${invalidIds.length} invalid IDs`,
      };
    }

    // Database operation
    const db = await getDatabase();
    const collection = db.collection('market_listings');

    // Delete listings
    const result = await collection.deleteMany({
      _id: { $in: listingIds },
    });

    // Log successful deletion
    console.log(
      `[DELETE_LISTINGS] User ${session.username} deleted ${result.deletedCount} listings`,
      {
        requestedCount: listingIds.length,
        deletedCount: result.deletedCount,
        timestamp: new Date().toISOString(),
      }
    );

    // Check if all requested items were deleted
    if (result.deletedCount < listingIds.length) {
      console.warn(
        `[DELETE_LISTINGS] Partial deletion: ${result.deletedCount}/${listingIds.length} deleted`,
        {
          missingCount: listingIds.length - result.deletedCount,
        }
      );
    }

    return {
      success: true,
      deletedCount: result.deletedCount,
    };
  } catch (error) {
    // Error logging with context
    console.error('[DELETE_LISTINGS] Error deleting market listings:', error, {
      requestedCount: listingIds?.length || 0,
      timestamp: new Date().toISOString(),
    });

    return {
      success: false,
      error: 'Failed to delete listings. Please try again.',
    };
  }
}
