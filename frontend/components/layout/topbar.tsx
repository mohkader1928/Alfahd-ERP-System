"use client";

import { useRouter } from "next/navigation";
import { Moon, Sun, Languages, LogOut, Building2, Repeat } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useI18n } from "@/lib/i18n/config";
import { useTheme } from "@/lib/theme";
import { useAuthStore } from "@/stores/auth-store";
import { useCompanyName } from "@/hooks/use-company-name";
import { decodeAccessToken } from "@/lib/jwt";

export function Topbar() {
  const { t, toggleLocale } = useI18n();
  const { theme, toggleTheme } = useTheme();
  const router = useRouter();
  const logout = useAuthStore((s) => s.logout);
  const accessToken = useAuthStore((s) => s.accessToken);

  // Which company you're in must be visible at all times, not just
  // implicit — see docs/18-ui-ux-audit.md, Company Context findings.
  const { name: companyName } = useCompanyName();

  // Only offer a switcher when there's actually something to switch
  // to — a single-company user (the common case today) should never see a
  // control for a choice they don't have.
  const authorizedCompanyCount = accessToken
    ? (decodeAccessToken(accessToken)?.authorized_companies.length ?? 1)
    : 1;

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <header className="flex h-14 items-center justify-between gap-2 border-b px-4">
      <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
        <Building2 className="h-4 w-4" />
        <span>{companyName ?? " "}</span>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" onClick={toggleLocale} title={t("locale.toggle")}>
          <Languages className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" onClick={toggleTheme} title={t("theme.toggle")}>
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
        <DropdownMenu>
          {/* This stack is Base UI (@base-ui/react), not Radix — polymorphism
              goes through the `render` prop, not `asChild`. Passing `asChild`
              here silently no-ops (React just warns about an unknown DOM
              attribute) and the Trigger renders its own default <button>
              around the child Button's <button>, producing an invalid
              nested-button hydration error. */}
          <DropdownMenuTrigger render={<Button variant="ghost" size="icon" />}>
            <LogOut className="h-4 w-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {authorizedCompanyCount > 1 && (
              <DropdownMenuItem onClick={() => router.push("/select-company")}>
                <Repeat className="h-4 w-4" />
                {t("nav.switch_company")}
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={handleLogout}>{t("nav.logout")}</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
