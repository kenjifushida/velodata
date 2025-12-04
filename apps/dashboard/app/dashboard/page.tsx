/**
 * Dashboard Page
 *
 * Main dashboard for viewing and filtering market listings.
 * Protected route - requires authentication.
 */
import { Suspense } from 'react';
import { getSession } from '@/lib/auth';
import { redirect } from 'next/navigation';
import { DashboardHeader } from '@/app/dashboard/components/DashboardHeader';
import { ListingsTable } from '@/app/dashboard/components/ListingsTable';
import { FilterPanel } from '@/app/dashboard/components/FilterPanel';
import { StatsCards } from '@/app/dashboard/components/StatsCards';
import { getListingStats } from '@/app/actions/market-listings';

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  // Verify authentication
  const session = await getSession();
  if (!session) {
    redirect('/login');
  }

  // Get dashboard stats
  const statsRaw = await getListingStats();
  const stats = {
    ...statsRaw,
    nicheBreakdown: (statsRaw.nicheBreakdown || []).map((d: any) => ({
      _id: String((d as any)._id ?? ''),
      count: Number((d as any).count ?? 0),
    })),
  };

  // Await searchParams for Next.js 15 compatibility
  const params = await searchParams;

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <DashboardHeader user={session} />

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Stats Section */}
        <div className="mb-8">
          <h2 className="mb-4 text-2xl font-bold text-zinc-900 dark:text-zinc-50">
            Overview
          </h2>
          <StatsCards stats={stats} />
        </div>

        {/* Listings Section */}
        <div className="mb-8">
          <h2 className="mb-4 text-2xl font-bold text-zinc-900 dark:text-zinc-50">
            Market Listings
          </h2>

          <div className="rounded-lg bg-white p-6 shadow dark:bg-zinc-900">
            {/* Filter Panel */}
            <Suspense fallback={<div>Loading filters...</div>}>
              <FilterPanel />
            </Suspense>

            {/* Listings Table */}
            <Suspense
              fallback={
                <div className="mt-6 flex items-center justify-center py-12">
                  <div className="text-zinc-600 dark:text-zinc-400">
                    Loading listings...
                  </div>
                </div>
              }
            >
              <ListingsTable searchParams={params} />
            </Suspense>
          </div>
        </div>
      </main>
    </div>
  );
}
