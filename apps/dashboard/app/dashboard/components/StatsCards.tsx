/**
 * Stats Cards Component
 *
 * Displays dashboard statistics in card format.
 */

interface StatsCardsProps {
  stats: {
    totalListings: number;
    processedListings: number;
    unprocessedListings: number;
    nicheBreakdown: Array<{ _id: string; count: number }>;
  };
}

export function StatsCards({ stats }: StatsCardsProps) {
  const nicheNames: Record<string, string> = {
    POKEMON_CARD: 'Pokemon Cards',
    WATCH: 'Watches',
    CAMERA_GEAR: 'Camera Gear',
  };

  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
      {/* Total Listings */}
      <div className="rounded-lg bg-white p-6 shadow dark:bg-zinc-900">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">
              Total Listings
            </p>
            <p className="mt-2 text-3xl font-bold text-zinc-900 dark:text-zinc-50">
              {stats.totalListings.toLocaleString()}
            </p>
          </div>
          <div className="rounded-full bg-blue-100 p-3 dark:bg-blue-900/20">
            <svg
              className="h-6 w-6 text-blue-600 dark:text-blue-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
          </div>
        </div>
      </div>

      {/* Processed */}
      <div className="rounded-lg bg-white p-6 shadow dark:bg-zinc-900">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">
              Processed
            </p>
            <p className="mt-2 text-3xl font-bold text-zinc-900 dark:text-zinc-50">
              {stats.processedListings.toLocaleString()}
            </p>
          </div>
          <div className="rounded-full bg-green-100 p-3 dark:bg-green-900/20">
            <svg
              className="h-6 w-6 text-green-600 dark:text-green-400"
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
          </div>
        </div>
      </div>

      {/* Unprocessed */}
      <div className="rounded-lg bg-white p-6 shadow dark:bg-zinc-900">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">
              Unprocessed
            </p>
            <p className="mt-2 text-3xl font-bold text-zinc-900 dark:text-zinc-50">
              {stats.unprocessedListings.toLocaleString()}
            </p>
          </div>
          <div className="rounded-full bg-yellow-100 p-3 dark:bg-yellow-900/20">
            <svg
              className="h-6 w-6 text-yellow-600 dark:text-yellow-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
        </div>
      </div>

      {/* Niche Breakdown */}
      <div className="rounded-lg bg-white p-6 shadow dark:bg-zinc-900">
        <p className="mb-3 text-sm font-medium text-zinc-600 dark:text-zinc-400">
          By Niche
        </p>
        <div className="space-y-2">
          {stats.nicheBreakdown.map((niche) => (
            <div key={niche._id} className="flex justify-between text-sm">
              <span className="text-zinc-700 dark:text-zinc-300">
                {nicheNames[niche._id] || niche._id}
              </span>
              <span className="font-semibold text-zinc-900 dark:text-zinc-50">
                {niche.count.toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
