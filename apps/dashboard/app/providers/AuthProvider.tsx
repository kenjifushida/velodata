/**
 * Auth Provider Component
 *
 * Initializes and syncs authentication state with Zustand store.
 * Runs on client-side to fetch session from server.
 */
'use client';

import { useEffect } from 'react';
import { useAuthStore } from '@/lib/store/auth-store';
import { getSessionAction } from '@/app/actions/auth';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const setUser = useAuthStore((state) => state.setUser);
  const setLoading = useAuthStore((state) => state.setLoading);

  useEffect(() => {
    // Sync session from server on mount
    getSessionAction()
      .then((session) => {
        setUser(session);
      })
      .catch((error) => {
        console.error('Failed to fetch session:', error);
        setUser(null);
      });
  }, [setUser, setLoading]);

  return <>{children}</>;
}
