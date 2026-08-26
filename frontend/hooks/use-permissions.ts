"use client";

import { useQuery } from "@tanstack/react-query";
import { identityApi } from "@/features/identity/api/client";
import { useAuthStore } from "@/stores/auth-store";
import { decodeAccessToken } from "@/lib/jwt";

/**
 * Phase 17A: single source of truth for "can the current user do X" in the
 * UI. Backed by GET /identity/me/permissions (self-scoped, always allowed
 * for any authenticated caller). This is UX only — every mutating endpoint
 * still enforces its own `require_permission()` server-side regardless of
 * what this hook returns, so a stale/absent cache here can only ever hide
 * an action the user was already forbidden from completing, never expose one.
 *
 * Owner-reported: a user who signed in right after a different, more
 * narrowly-scoped user had been active in the same browser tab (no full
 * page reload between the two -- a plain client-side SPA navigation) saw
 * that PREVIOUS user's permissions, because this query was keyed only by
 * companyId. Two different users active on the same company share that
 * key, so React Query happily served the stale entry. Login/logout now
 * also clear the whole query cache as the real fix (lib/landing-route.ts,
 * app/(auth)/login/page.tsx, components/layout/topbar.tsx) -- the `sub`
 * (user id) claim is added to this key too, purely as a second, independent
 * line of defense: even if some future code path forgets to clear the
 * cache, two different users can never collide on the same cache entry.
 */
export function useMyPermissions() {
  const companyId = useAuthStore((s) => s.activeCompanyId);
  const branchId = useAuthStore((s) => s.activeBranchId);
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = accessToken ? decodeAccessToken(accessToken)?.sub : undefined;

  const query = useQuery({
    queryKey: ["me-permissions", userId, companyId],
    queryFn: () => identityApi.getMyPermissions(companyId!, branchId),
    enabled: !!companyId && !!userId,
    staleTime: 5 * 60 * 1000,
  });

  const codes = new Set(query.data?.permission_codes ?? []);

  return {
    ...query,
    can: (permissionCode: string) => codes.has(permissionCode),
    canAny: (permissionCodes: string[]) => permissionCodes.some((c) => codes.has(c)),
  };
}
