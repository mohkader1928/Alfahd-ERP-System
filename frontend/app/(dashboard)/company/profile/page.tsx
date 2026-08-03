"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FormView } from "@/components/erp/form-view/form-view";
import { EntityImageUpload } from "@/components/erp/entity-image/entity-image-upload";
import { Can } from "@/components/erp/permissions/can";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { useCompanyName } from "@/hooks/use-company-name";
import { identityApi } from "@/features/identity/api/client";
import { ApiError } from "@/lib/api-client";
import { toastError, toastSuccess } from "@/lib/toast";

/**
 * UI/UX Evolution milestone — Entity Media Foundation (Company Logo). The
 * first real "company profile" screen in the app — before this there was
 * no page to manage anything about the active company beyond what
 * /bootstrap set once. Deliberately minimal: only the logo is editable
 * here, because no company-details PATCH endpoint exists yet (out of
 * scope for this milestone, not silently added) — legal name/VAT are
 * shown read-only for context.
 */
export default function CompanyProfilePage() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const { company, name: displayName, isLoading } = useCompanyName();

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["company", companyId] });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => identityApi.uploadCompanyLogo(companyId, file),
    onSuccess: () => {
      invalidate();
      toastSuccess(t("toast.success_title"), t("company.profile.logo"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  const removeMutation = useMutation({
    mutationFn: () => identityApi.deleteCompanyLogo(companyId),
    onSuccess: () => {
      invalidate();
      toastSuccess(t("toast.success_title"), t("media.remove"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  return (
    <FormView
      title={t("company.profile.title")}
      breadcrumbs={[{ label: t("company.profile.title") }]}
    >
      <div className="space-y-1">
        <Label>{t("company.profile.logo")}</Label>
        <Can permission="company.manage" fallback={<p className="text-sm text-muted-foreground">{displayName}</p>}>
          <EntityImageUpload
            src={company?.logo_path}
            name={displayName ?? ""}
            shape="square"
            size="xl"
            isUploading={uploadMutation.isPending}
            isRemoving={removeMutation.isPending}
            onUpload={(file) => uploadMutation.mutate(file)}
            onRemove={company?.logo_path ? () => removeMutation.mutate() : undefined}
            disabled={isLoading}
          />
        </Can>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">{t("company.profile.legal_name")}</Label>
          <p className="text-sm">{locale === "ar" ? company?.legal_name_ar : company?.legal_name}</p>
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">{t("company.profile.vat_number")}</Label>
          <p className="text-sm">{company?.vat_number}</p>
        </div>
      </div>
    </FormView>
  );
}
