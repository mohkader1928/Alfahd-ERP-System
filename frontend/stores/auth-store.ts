"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthorizedCompany {
  companyId: string;
  branchId: string | null;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  activeCompanyId: string | null;
  activeBranchId: string | null;
  hasHydrated: boolean;
  setTokens: (accessToken: string, refreshToken: string) => void;
  setActiveCompany: (companyId: string, branchId: string | null) => void;
  setHasHydrated: (value: boolean) => void;
  logout: () => void;
}

// Persisted to localStorage so a page refresh doesn't lose the session;
// api-client.ts reads the access token directly from localStorage (not
// through this store) to avoid a React-render dependency in a plain fetch
// wrapper — the store is the single writer, localStorage is the read path
// used outside React.
//
// `hasHydrated` matters because zustand's persist middleware rehydrates
// from localStorage *asynchronously* after the first render — on a fresh
// full-page load (not a client-side <Link> navigation), any guard that
// reads `accessToken` before rehydration finishes sees `null` and would
// wrongly redirect to /login even though the user is genuinely signed in.
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      activeCompanyId: null,
      activeBranchId: null,
      hasHydrated: false,
      setTokens: (accessToken, refreshToken) => {
        window.localStorage.setItem("erp.access_token", accessToken);
        set({ accessToken, refreshToken });
      },
      setActiveCompany: (companyId, branchId) => set({ activeCompanyId: companyId, activeBranchId: branchId }),
      setHasHydrated: (value) => set({ hasHydrated: value }),
      logout: () => {
        window.localStorage.removeItem("erp.access_token");
        set({ accessToken: null, refreshToken: null, activeCompanyId: null, activeBranchId: null });
      },
    }),
    {
      name: "erp.auth",
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        activeCompanyId: state.activeCompanyId,
        activeBranchId: state.activeBranchId,
      }),
    }
  )
);
