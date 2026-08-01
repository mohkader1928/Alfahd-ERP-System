"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FormView } from "@/components/erp/form-view/form-view";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { ApiError } from "@/lib/api-client";

export default function NewPartnerPage() {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialKind = searchParams.get("kind") === "vendor" ? "vendor" : "customer";
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [nameAr, setNameAr] = useState("");
  const [isCustomer, setIsCustomer] = useState(initialKind === "customer");
  const [isVendor, setIsVendor] = useState(initialKind === "vendor");
  const [vatNumber, setVatNumber] = useState("");
  const [crNumber, setCrNumber] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      identityApi.createPartner(companyId, branchId, {
        name,
        name_ar: nameAr || null,
        is_customer: isCustomer,
        is_vendor: isVendor,
        vat_number: vatNumber || null,
        cr_number: crNumber || null,
      }),
    onSuccess: (partner) => {
      queryClient.invalidateQueries({ queryKey: ["partners", companyId] });
      router.push(`/master-data/partners/${partner.id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  const backHref = initialKind === "vendor" ? "/master-data/vendors" : "/master-data/customers";

  return (
    <FormView
      title={initialKind === "vendor" ? t("master_data.vendors.new") : t("master_data.customers.new")}
      breadcrumbs={[
        { label: t("nav.master_data") },
        { label: initialKind === "vendor" ? t("master_data.vendors.title") : t("master_data.customers.title"), href: backHref },
        { label: t("common.new") },
      ]}
      onSave={() => {
        setError(null);
        createMutation.mutate();
      }}
      onCancel={() => router.push(backHref)}
      isSaving={createMutation.isPending}
      saveDisabled={!name || (!isCustomer && !isVendor)}
      error={error}
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1">
          <Label>{t("master_data.partners.name")}</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label>{t("master_data.partners.name_ar")}</Label>
          <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} dir="rtl" />
        </div>
        <div className="space-y-1">
          <Label>{t("master_data.partners.vat_number")}</Label>
          <Input value={vatNumber} onChange={(e) => setVatNumber(e.target.value)} maxLength={15} />
        </div>
        <div className="space-y-1">
          <Label>{t("master_data.partners.cr_number")}</Label>
          <Input value={crNumber} onChange={(e) => setCrNumber(e.target.value)} />
        </div>
        <div className="flex items-center gap-4 sm:col-span-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={isCustomer} onChange={(e) => setIsCustomer(e.target.checked)} />
            {t("master_data.partners.is_customer")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={isVendor} onChange={(e) => setIsVendor(e.target.checked)} />
            {t("master_data.partners.is_vendor")}
          </label>
        </div>
      </div>
    </FormView>
  );
}
