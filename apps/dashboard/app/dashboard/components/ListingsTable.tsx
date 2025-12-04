/**
 * Listings Table Component
 *
 * Server component that fetches data and passes to client component.
 */
import { getMarketListings } from '@/app/actions/market-listings';
import type { MarketListingFilters } from '@/lib/models/market-listing';
import { Pagination } from './Pagination';
import { ListingsTableClient } from './ListingsTableClient';

interface ListingsTableProps {
  searchParams: { [key: string]: string | string[] | undefined };
}

export async function ListingsTable({ searchParams }: ListingsTableProps) {
  // Parse search params into filters
  const filters: MarketListingFilters = {
    niche_type: searchParams.niche_type as any,
    source_id: searchParams.source_id as any,
    min_price: searchParams.min_price ? Number(searchParams.min_price) : undefined,
    max_price: searchParams.max_price ? Number(searchParams.max_price) : undefined,
    search: searchParams.search as string,
    is_processed:
      searchParams.is_processed === 'true'
        ? true
        : searchParams.is_processed === 'false'
        ? false
        : undefined,
    page: searchParams.page ? Number(searchParams.page) : 1,
    limit: 20,
  };

  const response = await getMarketListings(filters);

  if (response.listings.length === 0) {
    return (
      <div className="mt-6 flex flex-col items-center justify-center py-12">
        <svg
          className="mb-4 h-12 w-12 text-zinc-400 dark:text-zinc-600"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
          />
        </svg>
        <p className="text-lg font-medium text-zinc-900 dark:text-zinc-50">
          No listings found
        </p>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Try adjusting your filters or search criteria
        </p>
      </div>
    );
  }

  return (
    <div className="mt-6">
      {/* Results Count */}
      <div className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
        Showing {response.listings.length} of {response.total.toLocaleString()} listings
      </div>

      {/* Table with selection and export */}
      <ListingsTableClient listings={response.listings} />

      {/* Pagination */}
      <Pagination
        currentPage={response.page}
        totalPages={response.totalPages}
        total={response.total}
      />
    </div>
  );
}
