/**
 * Dashboard Header Component
 *
 * Top navigation bar with user info and logout button.
 */
'use client';

import { logoutAction } from '@/app/actions/auth';
import type { UserSession } from '@/lib/models/user';

interface DashboardHeaderProps {
  user: UserSession;
}

export function DashboardHeader({ user }: DashboardHeaderProps) {
  const handleLogout = async () => {
    await logoutAction();
  };

  return (
    <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        <div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-50">
            VeloData Dashboard
          </h1>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            High-frequency arbitrage platform
          </p>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
              {user.username}
            </p>
            <p className="text-xs text-zinc-600 dark:text-zinc-400">Logged in</p>
          </div>

          <button
            onClick={handleLogout}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:ring-offset-2 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200 dark:focus:ring-zinc-50"
          >
            Logout
          </button>
        </div>
      </div>
    </header>
  );
}
