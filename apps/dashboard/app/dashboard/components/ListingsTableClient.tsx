/**
 * Listings Table Client Component
 *
 * Client-side wrapper for listings table with selection and export functionality.
 */
'use client';

import { useState } from 'react';
import Image from 'next/image';
import type { MarketListing } from '@/lib/models/market-listing';
import { exportToEBayCSV } from '@/app/actions/export';

interface ListingsTableClientProps {
  listings: MarketListing[];
}

export function ListingsTableClient({ listings }: ListingsTableClientProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isExporting, setIsExporting] = useState(false);

  const nicheNames: Record<string, string> = {
    POKEMON_CARD: 'Pokemon Cards',
    WATCH: 'Watches',
    CAMERA_GEAR: 'Camera Gear',
  };

  const conditionColors: Record<string, string> = {
    N: 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400',
    S: 'bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400',
    A: 'bg-purple-100 text-purple-800 dark:bg-purple-900/20 dark:text-purple-400',
    B: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400',
    C: 'bg-orange-100 text-orange-800 dark:bg-orange-900/20 dark:text-orange-400',
    D: 'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400',
    JUNK: 'bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-400',
  };

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(new Set(listings.map((l) => l._id)));
    } else {
      setSelectedIds(new Set());
    }
  };

  const handleSelectOne = (id: string, checked: boolean) => {
    const newSelected = new Set(selectedIds);
    if (checked) {
      newSelected.add(id);
    } else {
      newSelected.delete(id);
    }
    setSelectedIds(newSelected);
  };

  const handleExport = async () => {
    if (selectedIds.size === 0) {
      alert('Please select at least one listing to export');
      return;
    }

    setIsExporting(true);

    try {
      const result = await exportToEBayCSV(Array.from(selectedIds));

      if (result.success && result.csv && result.filename) {
        // Create download link
        const blob = new Blob([result.csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = result.filename;
        link.click();
        URL.revokeObjectURL(url);

        // Clear selection
        setSelectedIds(new Set());
      } else {
        alert(result.error || 'Failed to export listings');
      }
    } catch (error) {
      console.error('Export error:', error);
      alert('An error occurred while exporting');
    } finally {
      setIsExporting(false);
    }
  };

  const allSelected = listings.length > 0 && selectedIds.size === listings.length;
  const someSelected = selectedIds.size > 0 && selectedIds.size < listings.length;

  return (
    <div>
      {/* Export Button */}
      {selectedIds.size > 0 && (
        <div className="mb-4 flex items-center justify-between rounded-lg bg-blue-50 p-4 dark:bg-blue-900/20">
          <span className="text-sm font-medium text-blue-900 dark:text-blue-100">
            {selectedIds.size} {selectedIds.size === 1 ? 'item' : 'items'} selected
          </span>
          <button
            onClick={handleExport}
            disabled={isExporting}
            className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-blue-500 dark:hover:bg-blue-600"
          >
            {isExporting ? (
              <>
                <svg
                  className="h-4 w-4 animate-spin"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                Exporting...
              </>
            ) : (
              <>
                <svg
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
                Export to eBay CSV
              </>
            )}
          </button>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-zinc-200 dark:border-zinc-800">
              <th className="px-4 py-3 text-left">
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={(input) => {
                    if (input) {
                      input.indeterminate = someSelected;
                    }
                  }}
                  onChange={(e) => handleSelectAll(e.target.checked)}
                  className="h-4 w-4 rounded border-zinc-300 text-blue-600 focus:ring-2 focus:ring-blue-500 dark:border-zinc-700"
                />
              </th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                Image
              </th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                Title
              </th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                Niche
              </th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                Source
              </th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                Price
              </th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                Condition
              </th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                Status
              </th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {listings.map((listing) => (
              <tr
                key={listing._id}
                className="border-b border-zinc-200 transition hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
              >
                <td className="px-4 py-4">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(listing._id)}
                    onChange={(e) => handleSelectOne(listing._id, e.target.checked)}
                    className="h-4 w-4 rounded border-zinc-300 text-blue-600 focus:ring-2 focus:ring-blue-500 dark:border-zinc-700"
                  />
                </td>
                <td className="px-4 py-4">
                  {listing.image_url ? (
                    <Image
                      src={listing.image_url}
                      alt={listing.title}
                      width={60}
                      height={60}
                      className="rounded-lg object-cover"
                    />
                  ) : (
                    <div className="flex h-[60px] w-[60px] items-center justify-center rounded-lg bg-zinc-200 dark:bg-zinc-700">
                      <svg
                        className="h-6 w-6 text-zinc-400 dark:text-zinc-500"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                        />
                      </svg>
                    </div>
                  )}
                </td>
                <td className="px-4 py-4">
                  <div className="max-w-xs">
                    <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-50">
                      {listing.title}
                    </p>
                    {listing.attributes.brand && (
                      <p className="text-xs text-zinc-600 dark:text-zinc-400">
                        {listing.attributes.brand}
                      </p>
                    )}
                  </div>
                </td>
                <td className="px-4 py-4">
                  <span className="text-sm text-zinc-700 dark:text-zinc-300">
                    {nicheNames[listing.niche_type] || listing.niche_type}
                  </span>
                </td>
                <td className="px-4 py-4">
                  <span className="text-sm text-zinc-700 dark:text-zinc-300">
                    {listing.source.display_name}
                  </span>
                </td>
                <td className="px-4 py-4">
                  <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                    ¥{listing.price_jpy.toLocaleString()}
                  </span>
                </td>
                <td className="px-4 py-4">
                  {listing.attributes.condition_rank && (
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                        conditionColors[listing.attributes.condition_rank] ||
                        'bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-400'
                      }`}
                    >
                      {listing.attributes.condition_rank}
                    </span>
                  )}
                </td>
                <td className="px-4 py-4">
                  {listing.is_processed ? (
                    <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                      <svg
                        className="h-4 w-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                      Processed
                    </span>
                  ) : (
                    <span className="text-xs text-zinc-600 dark:text-zinc-400">
                      Pending
                    </span>
                  )}
                </td>
                <td className="px-4 py-4">
                  <a
                    href={listing.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
                  >
                    View
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
