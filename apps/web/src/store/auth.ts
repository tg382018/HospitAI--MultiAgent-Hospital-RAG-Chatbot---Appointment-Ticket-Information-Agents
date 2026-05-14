import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type AuthTokens = {
  accessToken: string;
  refreshToken: string;
};

export type AuthStore = AuthTokens & {
  tenantSlug: string;
  setTenantSlug: (slug: string) => void;
  setTokens: (t: AuthTokens) => void;
  clear: () => void;
};

const empty: AuthTokens = { accessToken: '', refreshToken: '' };

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      ...empty,
      tenantSlug: 'demo-hospital',
      setTenantSlug: (tenantSlug) => set({ tenantSlug }),
      setTokens: ({ accessToken, refreshToken }) => set({ accessToken, refreshToken }),
      clear: () => set({ ...empty }),
    }),
    { name: 'hospitai-auth' }
  )
);
