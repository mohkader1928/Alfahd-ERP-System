"use client";

import { useQuery } from "@tanstack/react-query";
import { identityApi } from "@/features/identity/api/client";
import { useAuthStore } from "@/stores/auth-store";

/**
 * Phase 17A: single source of truth for "can the current user do X" in the
 * UI. Backed by GET /identity/me/permissions (self-scoped, always allowed
 * for any authenticated caller). This is UX only — every mutating endpoint
 * still enforces its own `require_permission()` server-side regardless of
 * what this hook returns, so a stale/absent cache here can only ever hide
 * an action the user was already forbidden from completing, never expose one.
 */
export function useMyPermissions() {
  const companyId = useAuthStore((s) => s.activeCompanyId);
  const branchId = useAuthStore((s) => s.activeBranchId);

  const query = useQuery({
    queryKey: ["me-permissions", companyId],
    queryFn: () => identityApi.getMyPermissions(companyId!, branchId),
    enabled: !!companyId,
    staleTime: 5 * 60 * 1000,
  });

  const codes = new Set(query.data?.permission_codes ?? []);

  return {
    ...query,
    can: (permissionCode: string) => codes.has(permissionCode),
    canAny: (permissionCodes: string[]) => permissionCodes.some((c) => codes.has(c)),
  };
}
