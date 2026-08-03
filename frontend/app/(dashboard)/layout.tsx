"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { useAuthStore } from "@/stores/auth-store";

/**
 * Client-side route protection: the access token lives in localStorage
 * (read directly by api-client.ts's plain fetch wrapper, outside React), so
 * a Next.js Proxy (server-side, Phase 9's renamed middleware.ts in Next 16)
 * can't see it without also duplicating the token into a cookie. For the
 * nucleus this layout-level guard is sufficient; a cookie + Proxy-based
 * check is a reasonable hardening follow-up if SSR-protected routes are
 * needed later.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const accessToken = useAuthStore((s) => s.accessToken);
  const activeCompanyId = useAuthStore((s) => s.activeCompanyId);
  const hasHydrated = useAuthStore((s) => s.hasHydrated);

  useEffect(() => {
    // Only decide once the persisted store has actually finished loading
    // from localStorage — see the store's comment on why this matters for
    // a fresh full-page load (vs. a client-side navigation that already
    // has the store populated in memory).
    if (hasHydrated && !accessToken) router.replace("/login");
  }, [hasHydrated, accessToken, router]);

  if (!hasHydrated) return null;
  if (!accessToken || !activeCompanyId) return null;

  return (
    <div className="flex flex-1">
      {/* Printing (e.g. the Subledger "Print statement" button) must show
          only the report content, not the app's own navigation chrome —
          neither was hidden before, so a printed page included the
          sidebar and topbar. */}
      <div className="print:hidden">
        <Sidebar />
      </div>
      <div className="flex flex-1 flex-col">
        <div className="print:hidden">
          <Topbar />
        </div>
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}
