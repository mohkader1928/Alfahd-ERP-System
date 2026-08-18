"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SettingsShell } from "@/components/erp/settings-shell/settings-shell";
import { FormView } from "@/components/erp/form-view/form-view";
import { EntityImageUpload } from "@/components/erp/entity-image/entity-image-upload";
import { Can } from "@/components/erp/permissions/can";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n/config";
import { useMyPermissions } from "@/hooks/use-permissions";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { ApiError } from "@/lib/api-client";
import { toastError, toastSuccess } from "@/lib/toast";
import type { Company } from "@/features/identity/api/types";

/**
 * Settings Architecture Foundation milestone. Supersedes the earlier
 * /company/profile screen (Entity Media Foundation milestone) — that page
 * only ever showed legal_name/vat_number read-only because no PATCH
 * endpoint existed yet; now that one does, Company Settings is the single
 * real place to manage a company's own details, living inside the
 * SettingsShell like every future settings area will.
 */
export default function CompanySettingsPage() {
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const companyQuery = useQuery({
    queryKey: ["company", companyId],
    queryFn: () => identityApi.getCompany(companyId),
  });

  if (companyQuery.isLoading || !companyQuery.data) {
    return (
      <SettingsShell>
        <Skeleton className="h-64 w-full" />
      </SettingsShell>
    );
  }

  return (
    <SettingsShell>
      <CompanySettingsForm company={companyQuery.data} companyId={companyId} />
    </SettingsShell>
  );
}

function CompanySettingsForm({ company, companyId }: { company: Company; companyId: string }) {
  const { t, locale } = useI18n();
  const queryClient = useQueryClient();
  const { can } = useMyPermissions();
  const canManage = can("company.manage");

  const [legalName, setLegalName] = useState(company.legal_name);
  const [legalNameAr, setLegalNameAr] = useState(company.legal_name_ar);
  const [vatNumber, setVatNumber] = useState(company.vat_number);
  const [crNumber, setCrNumber] = useState(company.cr_number ?? "");
  const [poApprovalThreshold, setPoApprovalThreshold] = useState(company.po_approval_threshold ?? "");
  const [fiscalYearStartMonth, setFiscalYearStartMonth] = useState(String(company.fiscal_year_start_month));
  const [error, setError] = useState<string | null>(null);

  const monthLabel = (month: number) => new Intl.DateTimeFormat(locale, { month: "long" }).format(new Date(2000, month - 1, 1));

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["company", companyId] });

  const saveMutation = useMutation({
    mutationFn: () =>
      identityApi.updateCompany(companyId, {
        legal_name: legalName,
        legal_name_ar: legalNameAr,
        vat_number: vatNumber,
        cr_number: crNumber || null,
        po_approval_threshold: poApprovalThreshold || null,
        fiscal_year_start_month: Number(fiscalYearStartMonth),
      }),
    onSuccess: () => {
      invalidate();
      toastSuccess(t("toast.success_title"), t("settings.company.saved"));
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  const uploadLogoMutation = useMutation({
    mutationFn: (file: File) => identityApi.uploadCompanyLogo(companyId, file),
    onSuccess: () => {
      invalidate();
      toastSuccess(t("toast.success_title"), t("company.profile.logo"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  const removeLogoMutation = useMutation({
    mutationFn: () => identityApi.deleteCompanyLogo(companyId),
    onSuccess: () => {
      invalidate();
      toastSuccess(t("toast.success_title"), t("media.remove"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  return (
    <FormView
      title={t("settings.section.company")}
      onSave={
        canManage
          ? () => {
              setError(null);
              saveMutation.mutate();
            }
          : undefined
      }
      isSaving={saveMutation.isPending}
      saveDisabled={!legalName || !legalNameAr || vatNumber.length !== 15}
      error={error}
    >
      <div className="space-y-1">
        <Label>{t("company.profile.logo")}</Label>
        <Can permission="company.manage" fallback={<p className="text-sm text-muted-foreground">{company.legal_name}</p>}>
          <EntityImageUpload
            src={company.logo_path}
            name={company.legal_name}
            shape="square"
            size="xl"
            isUploading={uploadLogoMutation.isPending}
            isRemoving={removeLogoMutation.isPending}
            onUpload={(file) => uploadLogoMutation.mutate(file)}
            onRemove={company.logo_path ? () => removeLogoMutation.mutate() : undefined}
          />
        </Can>
      </div>

      <div className="space-y-1">
        <Label className="text-xs text-muted-foreground">{t("settings.company.code")}</Label>
        <p className="font-mono text-sm tabular-nums">{company.code}</p>
        <p className="text-xs text-muted-foreground">{t("settings.company.code_hint")}</p>
      </div>

      <Can
        permission="company.manage"
        fallback={
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">{t("company.profile.legal_name")}</Label>
              <p className="text-sm">{company.legal_name}</p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">{t("company.profile.vat_number")}</Label>
              <p className="text-sm">{company.vat_number}</p>
            </div>
          </div>
        }
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-1">
            <Label>{t("company.profile.legal_name")}</Label>
            <Input value={legalName} onChange={(e) => setLegalName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>{t("settings.company.legal_name_ar")}</Label>
            <Input value={legalNameAr} onChange={(e) => setLegalNameAr(e.target.value)} dir="rtl" />
          </div>
          <div className="space-y-1">
            <Label>{t("company.profile.vat_number")}</Label>
            <Input value={vatNumber} onChange={(e) => setVatNumber(e.target.value)} maxLength={15} />
          </div>
          <div className="space-y-1">
            <Label>{t("settings.company.cr_number")}</Label>
            <Input value={crNumber} onChange={(e) => setCrNumber(e.target.value)} />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label>{t("settings.company.po_approval_threshold")}</Label>
            <Input
              type="number"
              min="0"
              step="0.01"
              placeholder={t("settings.company.po_approval_threshold_placeholder")}
              value={poApprovalThreshold}
              onChange={(e) => setPoApprovalThreshold(e.target.value)}
              className="max-w-xs"
            />
            <p className="text-xs text-muted-foreground">{t("settings.company.po_approval_threshold_hint")}</p>
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label>{t("settings.company.fiscal_year_start_month")}</Label>
            <Select value={fiscalYearStartMonth} onValueChange={(v) => v && setFiscalYearStartMonth(v)}>
              <SelectTrigger className="max-w-xs">
                <SelectValue>{monthLabel(Number(fiscalYearStartMonth))}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {Array.from({ length: 12 }, (_, i) => i + 1).map((month) => (
                  <SelectItem key={month} value={String(month)}>
                    {monthLabel(month)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">{t("settings.company.fiscal_year_start_month_hint")}</p>
          </div>
        </div>
      </Can>
    </FormView>
  );
}
