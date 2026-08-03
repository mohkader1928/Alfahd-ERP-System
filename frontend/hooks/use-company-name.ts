"use client";

import { useQuery } from "@tanstack/react-query";
import { identityApi } from "@/features/identity/api/client";
import { useAuthStore } from "@/stores/auth-store";
import { useI18n } from "@/lib/i18n/config";

/**
 * UI/UX Foundation milestone: single source of truth for "what is the
 * active company's name, in the current locale" — before this, Topbar and
 * Dashboard each duplicated the same legal_name/legal_name_ar ternary, and
 * only Topbar's copy was actually locale-aware (docs/18-ui-ux-audit.md,
 * finding B2, confirmed live: same screen, two different names in Arabic).
 * Shares the same `["company", companyId]` query key already used
 * everywhere else this data is fetched, so switching the active company
 * refetches once and every consumer (Topbar, Dashboard, print headers)
 * updates together — no separate cache to go stale.
 */
export function useCompanyName() {
  const companyId = useAuthStore((s) => s.activeCompanyId);
  const { locale } = useI18n();

  const query = useQuery({
    queryKey: ["company", companyId],
    queryFn: () => identityApi.getCompany(companyId as string),
    enabled: !!companyId,
    staleTime: 5 * 60 * 1000,
  });

  const name = locale === "ar" ? query.data?.legal_name_ar : query.data?.legal_name;

  return { name, company: query.data, isLoading: query.isLoading };
}
