"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";

export default function RootPage() {
  const router = useRouter();
  const accessToken = useAuthStore((s) => s.accessToken);
  const hasHydrated = useAuthStore((s) => s.hasHydrated);

  useEffect(() => {
    // See stores/auth-store.ts: wait for persisted-state rehydration before
    // deciding, or a logged-in user hitting "/" fresh gets bounced to /login.
    if (!hasHydrated) return;
    router.replace(accessToken ? "/dashboard" : "/login");
  }, [hasHydrated, accessToken, router]);

  return null;
}
