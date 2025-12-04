/**
 * Server Actions for Authentication
 *
 * Handles login, logout, and session management.
 * These actions run on the server and can be called from client components.
 */
'use server';

import { redirect } from 'next/navigation';
import { getDatabase } from '@/lib/mongodb';
import { loginSchema, type User, type UserSession } from '@/lib/models/user';
import {
  verifyPassword,
  createSession,
  deleteSession,
  getSession,
} from '@/lib/auth';

export interface AuthResponse {
  success: boolean;
  error?: string;
  user?: UserSession;
}

/**
 * Login action - validates credentials and creates session
 */
export async function loginAction(
  _prevState: unknown,
  formData: FormData
): Promise<AuthResponse> {
  try {
    // Parse and validate form data
    const username = formData.get('username') as string;
    const password = formData.get('password') as string;

    const validation = loginSchema.safeParse({ username, password });

    if (!validation.success) {
      return {
        success: false,
        error: validation.error.issues[0].message,
      };
    }

    // Find user in database
    const db = await getDatabase();
    const usersCollection = db.collection<User>('users');

    const user = await usersCollection.findOne({ username: validation.data.username });

    if (!user) {
      return {
        success: false,
        error: 'Invalid username or password',
      };
    }

    // Verify password
    const isValidPassword = await verifyPassword(
      validation.data.password,
      user.password
    );

    if (!isValidPassword) {
      return {
        success: false,
        error: 'Invalid username or password',
      };
    }

    // Create session
    const userSession: UserSession = {
      id: user._id?.toString() || '',
      username: user.username,
    };

    await createSession(userSession);

    return {
      success: true,
      user: userSession,
    };
  } catch (error) {
    console.error('Login error:', error);
    return {
      success: false,
      error: 'An unexpected error occurred. Please try again.',
    };
  }
}

/**
 * Logout action - destroys session
 */
export async function logoutAction(): Promise<void> {
  await deleteSession();
  redirect('/login');
}

/**
 * Get current session (for client-side session sync)
 */
export async function getSessionAction(): Promise<UserSession | null> {
  return getSession();
}
