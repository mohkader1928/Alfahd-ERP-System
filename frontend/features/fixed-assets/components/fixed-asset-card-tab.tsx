"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { ReportView } from "@/components/erp/report-view/report-view";
import { ReportPrintHeader } from "@/components/erp/report-view/report-print-header";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { fixedAssetsApi } from "@/features/fixed-assets/api/client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { reportExportHandlers } from "@/lib/report-export";

/** بطاقة الأصل الثابت — same opening/running/closing shape as the
 * Customer/Vendor Subledger and Product Cardex, but tracking three
 * parallel running values (cost, accumulated depreciation, net book
 * value) since a fixed asset's movements come from two sources: the
 * asset row itself (acquisition/disposal) and its depreciation entries. */
export function FixedAssetCardTab({ initialAssetId }: { initialAssetId?: string }) {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const [dateFrom, setDateFrom] = useState(() => `${new Date().getFullYear()}-01-01`);
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [assetId, setAssetId] = useState(initialAssetId ?? "");
  const [ranAt, setRanAt] = useState<{ asset: string; from: string; to: string } | null>(() =>
    initialAssetId ? { asset: initialAssetId, from: dateFrom, to: dateTo } : null
  );

  const assetsQuery = useQuery({
    queryKey: ["fixed-assets", companyId],
    queryFn: () => fixedAssetsApi.listAssets(companyId),
  });
  const cardQuery = useQuery({
    queryKey: ["fixed-asset-card", companyId, ranAt?.asset, ranAt?.from, ranAt?.to],
    queryFn: () => fixedAssetsApi.getAssetCard(companyId, ranAt!.asset, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });
  const r = cardQuery.data;

  return (
    <ReportView
      title={t("fixed_assets.card.title")}
      filterArea={
        <>
          <div className="w-64 space-y-1">
            <Label className="text-xs">{t("fixed_assets.card.select_asset")}</Label>
            <Select value={assetId} onValueChange={(v) => setAssetId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("fixed_assets.card.select_asset")}>
                  {(value: string) => {
                    const asset = assetsQuery.data?.find((a) => a.id === value);
                    return asset ? `${asset.asset_code} — ${asset.name}` : value;
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {assetsQuery.data?.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.asset_code} — {a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.tb.date_from")}</Label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.tb.date_to")}</Label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
        </>
      }
      onApply={assetId ? () => setRanAt({ asset: assetId, from: dateFrom, to: dateTo }) : undefined}
      onPrint={ranAt && r ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            `/api/v1/fixed-assets/${ranAt.asset}/card`,
            { date_from: ranAt.from, date_to: ranAt.to, lang: locale },
            companyId
          )
        : {})}
      isLoading={cardQuery.isLoading}
      isError={cardQuery.isError}
      onRetry={() => cardQuery.refetch()}
      kpis={
        r
          ? [
              { label: t("fixed_assets.cost"), value: formatCurrency(r.closing_cost) },
              { label: t("fixed_assets.accumulated_depreciation"), value: formatCurrency(r.closing_accumulated_depreciation) },
              { label: t("fixed_assets.net_book_value"), value: formatCurrency(r.closing_net_book_value) },
            ]
          : undefined
      }
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("fixed_assets.card.select_asset_hint")}</p>}
      {ranAt && r && (
        <>
          <ReportPrintHeader
            reportTitle={t("fixed_assets.card.title")}
            subtitle={`${r.asset_code} — ${r.asset_name}`}
            dateRangeLabel={`${r.date_from} – ${r.date_to}`}
          />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("accounting.sub.date")}</TableHead>
                <TableHead>{t("fixed_assets.card.movement_type")}</TableHead>
                <TableHead>{t("accounting.sub.reference")}</TableHead>
                <TableHead className="text-end">{t("fixed_assets.cost")}</TableHead>
                <TableHead className="text-end">{t("fixed_assets.accumulated_depreciation")}</TableHead>
                <TableHead className="text-end">{t("fixed_assets.net_book_value")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow className="italic text-muted-foreground">
                <TableCell colSpan={3}>{t("accounting.sub.opening_balance")}</TableCell>
                <TableCell className="text-end font-mono">{formatCurrency(r.opening_cost)}</TableCell>
                <TableCell className="text-end font-mono">{formatCurrency(r.opening_accumulated_depreciation)}</TableCell>
                <TableCell className="text-end font-mono">{formatCurrency(r.opening_net_book_value)}</TableCell>
              </TableRow>
              {r.lines.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    {t("common.empty")}
                  </TableCell>
                </TableRow>
              )}
              {r.lines.map((line, i) => (
                <TableRow key={i}>
                  <TableCell>{formatDate(line.date, locale)}</TableCell>
                  <TableCell>{t(`fixed_assets.card.movement.${line.movement_type}`)}</TableCell>
                  <TableCell>{line.reference}</TableCell>
                  <TableCell className="text-end font-mono">{formatCurrency(line.running_cost)}</TableCell>
                  <TableCell className="text-end font-mono">
                    {formatCurrency(line.running_accumulated_depreciation)}
                  </TableCell>
                  <TableCell className="text-end font-mono">{formatCurrency(line.running_net_book_value)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow className="font-semibold">
                <TableCell colSpan={3}>{t("accounting.sub.closing_balance")}</TableCell>
                <TableCell className="text-end font-mono">{formatCurrency(r.closing_cost)}</TableCell>
                <TableCell className="text-end font-mono">{formatCurrency(r.closing_accumulated_depreciation)}</TableCell>
                <TableCell className="text-end font-mono">{formatCurrency(r.closing_net_book_value)}</TableCell>
              </TableRow>
            </TableFooter>
          </Table>
        </>
      )}
    </ReportView>
  );
}
