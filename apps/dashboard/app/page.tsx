/**
 * Home Page - Redirects to Dashboard
 *
 * Root page that redirects authenticated users to dashboard
 * and unauthenticated users to login (via middleware).
 */
import { redirect } from 'next/navigation';

export default function Home() {
  redirect('/dashboard');
}
