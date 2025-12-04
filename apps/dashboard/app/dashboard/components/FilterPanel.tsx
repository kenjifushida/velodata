/**
 * Filter Panel Component
 *
 * Provides filtering and search UI for market listings.
 */
'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useState, useEffect } from 'react';
import { getFilterOptions } from '@/app/actions/market-listings';
import type { NicheType, SourceId } from '@/lib/models/market-listing';

export function FilterPanel() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [search, setSearch] = useState(searchParams.get('search') || '');
  const [nicheType, setNicheType] = useState(searchParams.get('niche_type') || '');
  const [sourceId, setSourceId] = useState(searchParams.get('source_id') || '');
  const [minPrice, setMinPrice] = useState(searchParams.get('min_price') || '');
  const [maxPrice, setMaxPrice] = useState(searchParams.get('max_price') || '');
  const [isProcessed, setIsProcessed] = useState(searchParams.get('is_processed') || '');

  const [filterOptions, setFilterOptions] = useState<{
    nicheTypes: NicheType[];
    sources: SourceId[];
    priceRange: { min_price: number; max_price: number };
  }>({
    nicheTypes: [],
    sources: [],
    priceRange: { min_price: 0, max_price: 100000 },
  });

  // Load filter options on mount
  useEffect(() => {
    getFilterOptions().then(setFilterOptions);
  }, []);

  const handleApplyFilters = () => {
    const params = new URLSearchParams();

    if (search) params.set('search', search);
    if (nicheType) params.set('niche_type', nicheType);
    if (sourceId) params.set('source_id', sourceId);
    if (minPrice) params.set('min_price', minPrice);
    if (maxPrice) params.set('max_price', maxPrice);
    if (isProcessed) params.set('is_processed', isProcessed);

    router.push(`/dashboard?${params.toString()}`);
  };

  const handleClearFilters = () => {
    setSearch('');
    setNicheType('');
    setSourceId('');
    setMinPrice('');
    setMaxPrice('');
    setIsProcessed('');
    router.push('/dashboard');
  };

  const nicheNames: Record<string, string> = {
    POKEMON_CARD: 'Pokemon Cards',
    WATCH: 'Watches',
    CAMERA_GEAR: 'Camera Gear',
  };

  const sourceNames: Record<string, string> = {
    HARDOFF: 'Hard-Off',
    MERCARI_JP: 'Mercari Japan',
    YAHOO_AUCTIONS_JP: 'Yahoo! Auctions',
  };

  return (
    <div className="space-y-4">
      {/* Search Bar */}
      <div>
        <label
          htmlFor="search"
          className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
        >
          Search
        </label>
        <input
          id="search"
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by title or brand..."
          className="mt-1 block w-full rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:border-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder-zinc-500 dark:focus:border-zinc-500"
        />
      </div>

      {/* Filter Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {/* Niche Type */}
        <div>
          <label
            htmlFor="niche-type"
            className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            Niche
          </label>
          <select
            id="niche-type"
            value={nicheType}
            onChange={(e) => setNicheType(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm text-zinc-900 focus:border-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-zinc-500"
          >
            <option value="">All Niches</option>
            {filterOptions.nicheTypes.map((type) => (
              <option key={type} value={type}>
                {nicheNames[type] || type}
              </option>
            ))}
          </select>
        </div>

        {/* Source */}
        <div>
          <label
            htmlFor="source"
            className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            Source
          </label>
          <select
            id="source"
            value={sourceId}
            onChange={(e) => setSourceId(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm text-zinc-900 focus:border-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-zinc-500"
          >
            <option value="">All Sources</option>
            {filterOptions.sources.map((source) => (
              <option key={source} value={source}>
                {sourceNames[source] || source}
              </option>
            ))}
          </select>
        </div>

        {/* Min Price */}
        <div>
          <label
            htmlFor="min-price"
            className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            Min Price (¥)
          </label>
          <input
            id="min-price"
            type="number"
            value={minPrice}
            onChange={(e) => setMinPrice(e.target.value)}
            placeholder="0"
            className="mt-1 block w-full rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:border-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder-zinc-500 dark:focus:border-zinc-500"
          />
        </div>

        {/* Max Price */}
        <div>
          <label
            htmlFor="max-price"
            className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            Max Price (¥)
          </label>
          <input
            id="max-price"
            type="number"
            value={maxPrice}
            onChange={(e) => setMaxPrice(e.target.value)}
            placeholder="1000000"
            className="mt-1 block w-full rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:border-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder-zinc-500 dark:focus:border-zinc-500"
          />
        </div>

        {/* Processing Status */}
        <div>
          <label
            htmlFor="is-processed"
            className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            Status
          </label>
          <select
            id="is-processed"
            value={isProcessed}
            onChange={(e) => setIsProcessed(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm text-zinc-900 focus:border-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-zinc-500"
          >
            <option value="">All Status</option>
            <option value="true">Processed</option>
            <option value="false">Unprocessed</option>
          </select>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex gap-3">
        <button
          onClick={handleApplyFilters}
          className="rounded-lg bg-zinc-900 px-6 py-2 text-sm font-semibold text-white transition hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:ring-offset-2 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          Apply Filters
        </button>
        <button
          onClick={handleClearFilters}
          className="rounded-lg border border-zinc-300 px-6 py-2 text-sm font-semibold text-zinc-700 transition hover:bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:ring-offset-2 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          Clear Filters
        </button>
      </div>
    </div>
  );
}
