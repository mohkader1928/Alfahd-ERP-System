"use client";

import { useRouter } from "next/navigation";
import { Moon, Sun, Languages, LogOut } from "lucide-react";
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

export function Topbar() {
  const { t, toggleLocale } = useI18n();
  const { theme, toggleTheme } = useTheme();
  const router = useRouter();
  const logout = useAuthStore((s) => s.logout);

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <header className="flex h-14 items-center justify-end gap-2 border-b px-4">
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
          <DropdownMenuItem onClick={handleLogout}>{t("nav.logout")}</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
