"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { reportingApi } from "@/features/reporting/api/client";
import { sourceDocumentHref } from "@/lib/source-document-links";
import type { SearchResultRow } from "@/features/reporting/api/types";

const TYPE_LABEL_KEYS: Record<string, string> = {
  partner: "search.type.partner",
  product: "search.type.product",
  sales_quotation: "search.type.sales_quotation",
  sales_order: "search.type.sales_order",
  sales_invoice: "search.type.sales_invoice",
  purchase_order: "search.type.purchase_order",
  vendor_bill: "search.type.vendor_bill",
};

/**
 * Professional Workspace Layer — Global Search. One box that crosses
 * every entity type instead of making the user already know which
 * module a customer/invoice/product lives in — the single most-missed
 * "feels like a real ERP" element found in the full-project audit.
 */
export function GlobalSearch() {
  const { t } = useI18n();
  const router = useRouter();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const [raw, setRaw] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(raw.trim()), 250);
    return () => clearTimeout(timer);
  }, [raw]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const searchQuery = useQuery({
    queryKey: ["global-search", companyId, debounced],
    queryFn: () => reportingApi.search(companyId, debounced),
    enabled: debounced.length >= 2,
  });

  const results = debounced.length >= 2 ? (searchQuery.data ?? []) : [];

  function goTo(row: SearchResultRow) {
    const href = sourceDocumentHref(row.type, row.id);
    if (href) {
      router.push(href);
      setRaw("");
      setDebounced("");
      setOpen(false);
    }
  }

  return (
    <div ref={containerRef} className="relative w-full max-w-sm">
      <div className="relative">
        <Search className="pointer-events-none absolute start-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={raw}
          onChange={(e) => {
            setRaw(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={t("search.placeholder")}
          className="h-8 ps-8 pe-8 text-sm"
        />
        {raw && (
          <button
            type="button"
            onClick={() => {
              setRaw("");
              setDebounced("");
            }}
            className="absolute end-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {open && debounced.length >= 2 && (
        <div className="absolute top-full z-50 mt-1 max-h-96 w-full overflow-y-auto rounded-md border bg-popover shadow-md">
          {searchQuery.isLoading && (
            <p className="px-3 py-2 text-sm text-muted-foreground">{t("common.loading")}</p>
          )}
          {!searchQuery.isLoading && results.length === 0 && (
            <p className="px-3 py-2 text-sm text-muted-foreground">{t("search.no_results")}</p>
          )}
          {!searchQuery.isLoading &&
            results.map((row) => (
              <button
                key={`${row.type}-${row.id}`}
                type="button"
                onClick={() => goTo(row)}
                className="flex w-full flex-col items-start gap-0 px-3 py-1.5 text-start text-sm hover:bg-muted"
              >
                <span className="font-medium">{row.label}</span>
                <span className="text-xs text-muted-foreground">
                  {t(TYPE_LABEL_KEYS[row.type] ?? row.type)}
                  {row.sublabel ? ` · ${row.sublabel}` : ""}
                </span>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
