/**
 * Filter Panel Component
 *
 * Provides filtering and search UI for market listings.
 */
'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useState, useEffect } from 'react';
import { getFilterOptions } from '@/app/actions/market-listings';
import type { NicheType, SourceId, TCGGame, GradingCompany } from '@/lib/models/market-listing';
import { NICHE_DISPLAY_NAMES, SOURCE_DISPLAY_NAMES, TCG_GAME_NAMES, GRADING_COMPANY_NAMES } from '@/lib/constants';

export function FilterPanel() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [search, setSearch] = useState(searchParams.get('search') || '');
  const [nicheType, setNicheType] = useState(searchParams.get('niche_type') || '');
  const [sourceId, setSourceId] = useState(searchParams.get('source_id') || '');
  const [minPrice, setMinPrice] = useState(searchParams.get('min_price') || '');
  const [maxPrice, setMaxPrice] = useState(searchParams.get('max_price') || '');
  const [isProcessed, setIsProcessed] = useState(searchParams.get('is_processed') || '');
  // TCG-specific filters
  const [tcgGame, setTcgGame] = useState(searchParams.get('tcg_game') || '');
  const [isGraded, setIsGraded] = useState(searchParams.get('is_graded') || '');
  const [gradingCompany, setGradingCompany] = useState(searchParams.get('grading_company') || '');

  const [filterOptions, setFilterOptions] = useState<{
    nicheTypes: NicheType[];
    sources: SourceId[];
    priceRange: { min_price: number; max_price: number };
    tcgGames: TCGGame[];
    gradingCompanies: GradingCompany[];
  }>({
    nicheTypes: [],
    sources: [],
    priceRange: { min_price: 0, max_price: 100000 },
    tcgGames: [],
    gradingCompanies: [],
  });

  // Load filter options on mount
  useEffect(() => {
    getFilterOptions().then(setFilterOptions);
  }, []);

  // Show TCG-specific filters when TCG niche is selected
  const showTcgFilters = nicheType === 'TCG';

  const handleApplyFilters = () => {
    const params = new URLSearchParams();

    if (search) params.set('search', search);
    if (nicheType) params.set('niche_type', nicheType);
    if (sourceId) params.set('source_id', sourceId);
    if (minPrice) params.set('min_price', minPrice);
    if (maxPrice) params.set('max_price', maxPrice);
    if (isProcessed) params.set('is_processed', isProcessed);
    // TCG-specific filters
    if (tcgGame) params.set('tcg_game', tcgGame);
    if (isGraded) params.set('is_graded', isGraded);
    if (gradingCompany) params.set('grading_company', gradingCompany);

    router.push(`/dashboard?${params.toString()}`);
  };

  const handleClearFilters = () => {
    setSearch('');
    setNicheType('');
    setSourceId('');
    setMinPrice('');
    setMaxPrice('');
    setIsProcessed('');
    // TCG-specific filters
    setTcgGame('');
    setIsGraded('');
    setGradingCompany('');
    router.push('/dashboard');
  };

  // Clear TCG filters when switching away from TCG niche
  const handleNicheChange = (value: string) => {
    setNicheType(value);
    if (value !== 'TCG') {
      setTcgGame('');
      setIsGraded('');
      setGradingCompany('');
    }
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
            onChange={(e) => handleNicheChange(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm text-zinc-900 focus:border-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-zinc-500"
          >
            <option value="">All Niches</option>
            {filterOptions.nicheTypes.map((type) => (
              <option key={type} value={type}>
                {NICHE_DISPLAY_NAMES[type] || type}
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
                {SOURCE_DISPLAY_NAMES[source] || source}
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

      {/* TCG-Specific Filters - shown when TCG niche is selected */}
      {showTcgFilters && (
        <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-900/20">
          <h3 className="mb-3 text-sm font-semibold text-blue-900 dark:text-blue-100">
            TCG Filters
          </h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {/* TCG Game */}
            <div>
              <label
                htmlFor="tcg-game"
                className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
              >
                Card Game
              </label>
              <select
                id="tcg-game"
                value={tcgGame}
                onChange={(e) => setTcgGame(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm text-zinc-900 focus:border-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-zinc-500"
              >
                <option value="">All Games</option>
                {filterOptions.tcgGames.map((game) => (
                  <option key={game} value={game}>
                    {TCG_GAME_NAMES[game] || game}
                  </option>
                ))}
              </select>
            </div>

            {/* Graded Filter */}
            <div>
              <label
                htmlFor="is-graded"
                className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
              >
                Grading
              </label>
              <select
                id="is-graded"
                value={isGraded}
                onChange={(e) => setIsGraded(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm text-zinc-900 focus:border-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-zinc-500"
              >
                <option value="">All Cards</option>
                <option value="true">Graded Only</option>
                <option value="false">Raw Only</option>
              </select>
            </div>

            {/* Grading Company */}
            <div>
              <label
                htmlFor="grading-company"
                className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
              >
                Grading Company
              </label>
              <select
                id="grading-company"
                value={gradingCompany}
                onChange={(e) => setGradingCompany(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm text-zinc-900 focus:border-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-zinc-500"
              >
                <option value="">All Companies</option>
                {filterOptions.gradingCompanies.map((company) => (
                  <option key={company} value={company}>
                    {GRADING_COMPANY_NAMES[company] || company}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      )}

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
