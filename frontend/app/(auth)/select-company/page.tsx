"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { decodeAccessToken } from "@/lib/jwt";
import { identityApi } from "@/features/identity/api/client";

interface CompanyEntry {
  companyId: string;
  branchId: string | null;
}

function CompanyOption({ entry, onSelect }: { entry: CompanyEntry; onSelect: () => void }) {
  const { locale } = useI18n();
  const query = useQuery({
    queryKey: ["company", entry.companyId],
    queryFn: () => identityApi.getCompany(entry.companyId),
    staleTime: 5 * 60 * 1000,
  });
  const name = locale === "ar" ? query.data?.legal_name_ar : query.data?.legal_name;

  return (
    <button
      type="button"
      onClick={onSelect}
      className="flex w-full items-center gap-3 rounded-md border p-3 text-start transition-colors hover:bg-muted"
    >
      <Building2 className="h-5 w-5 shrink-0 text-muted-foreground" />
      {query.isLoading ? <Skeleton className="h-4 w-40" /> : <span className="font-medium">{name ?? entry.companyId}</span>}
    </button>
  );
}

/**
 * UI/UX Foundation milestone — Company Context. Before this, login always
 * silently picked authorized_companies[0] with no way to see or choose a
 * second company (docs/18-ui-ux-audit.md, finding B1). Reachable two ways:
 * from login when authorized_companies.length > 1 (login/page.tsx), or
 * later from Topbar's "Switch company" menu item (only shown under the
 * same condition).
 */
export default function SelectCompanyPage() {
  const { t } = useI18n();
  const router = useRouter();
  const accessToken = useAuthStore((s) => s.accessToken);
  const hasHydrated = useAuthStore((s) => s.hasHydrated);
  const setActiveCompany = useAuthStore((s) => s.setActiveCompany);

  const entries: CompanyEntry[] = accessToken
    ? (decodeAccessToken(accessToken)?.authorized_companies ?? []).map((entry) => {
        const [companyId, branchId] = entry.split(":");
        return { companyId, branchId: branchId ?? null };
      })
    : [];

  useEffect(() => {
    // Same race the dashboard layout guards against: zustand's persist
    // middleware rehydrates from localStorage *asynchronously*, so on a
    // fresh full page load (a bookmark, a refresh, a new tab — not a
    // client-side navigation from login/Topbar, which already has a
    // hydrated store) accessToken reads as null for one render before the
    // real value loads. Acting on that null before hydration finishes
    // bounces an already-logged-in user to /login — found live while
    // re-verifying this exact page for the Company Context closeout.
    if (!hasHydrated) return;
    if (!accessToken) {
      router.replace("/login");
      return;
    }
    // Nothing to choose: a single-company user (the common case), or
    // anyone who somehow has zero — either way, don't leave them stuck on
    // a picker with nothing useful in it.
    if (entries.length === 1) {
      setActiveCompany(entries[0].companyId, entries[0].branchId);
      router.replace("/dashboard");
    } else if (entries.length === 0) {
      router.replace("/login");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasHydrated, accessToken, entries.length]);

  if (!hasHydrated || !accessToken || entries.length <= 1) return null;

  function handleSelect(entry: CompanyEntry) {
    setActiveCompany(entry.companyId, entry.branchId);
    router.push("/dashboard");
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("auth.company.select")}</CardTitle>
        <CardDescription>{t("auth.company.select_subtitle")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {entries.map((entry) => (
          <CompanyOption key={`${entry.companyId}:${entry.branchId ?? ""}`} entry={entry} onSelect={() => handleSelect(entry)} />
        ))}
      </CardContent>
    </Card>
  );
}
