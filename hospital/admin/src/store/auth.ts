import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { apiFetch } from '@/lib/api';

export type UserRole = 'admin' | 'staff' | 'doctor' | 'patient' | 'operator';

export type Me = {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  tenant_id: string;
};

type AuthState = {
  accessToken: string | null;
  me: Me | null;
  setSession: (access: string, me: Me) => void;
  clear: () => void;
};

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      me: null,
      setSession: (access, me) => set({ accessToken: access, me }),
      clear: () => set({ accessToken: null, me: null }),
    }),
    { name: 'hospitai-admin-auth' }
  )
);

export function authHeaders(token: string | null): HeadersInit {
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

export async function fetchMe(access: string): Promise<Me> {
  return apiFetch<Me>('/api/v1/users/me', { headers: authHeaders(access) });
}

export function canManageDocuments(role: UserRole | undefined): boolean {
  return role === 'admin' || role === 'staff';
}

export function canManageConnector(role: UserRole | undefined): boolean {
  return role === 'admin';
}

export function canTenantAdmin(role: UserRole | undefined): boolean {
  return role === 'admin';
}
