"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RecordCard } from "@/components/erp/record-card/record-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/erp/states/error-state";
import { NotFoundState } from "@/components/erp/states/not-found";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { ApiError } from "@/lib/api-client";
import type { Address, Partner } from "@/features/identity/api/types";

const EMPTY_ADDRESS: Address = { street: "", city: "", region: "", postal_code: "", country_code: "" };

export default function PartnerDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const partnerQuery = useQuery({
    queryKey: ["partner", companyId, id],
    queryFn: () => identityApi.getPartner(companyId, id),
  });

  if (partnerQuery.isError && partnerQuery.error instanceof ApiError && partnerQuery.error.status === 404) {
    return <NotFoundState label={t("master_data.partners.not_found")} />;
  }
  if (partnerQuery.isError) {
    return <ErrorState onRetry={() => partnerQuery.refetch()} />;
  }
  if (partnerQuery.isLoading || !partnerQuery.data) {
    return null;
  }

  return <PartnerEditForm key={partnerQuery.data.id} partner={partnerQuery.data} companyId={companyId} />;
}

function PartnerEditForm({ partner, companyId }: { partner: Partner; companyId: string }) {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [name, setName] = useState(partner.name);
  const [nameAr, setNameAr] = useState(partner.name_ar ?? "");
  const [isCustomer, setIsCustomer] = useState(partner.is_customer);
  const [isVendor, setIsVendor] = useState(partner.is_vendor);
  const [vatNumber, setVatNumber] = useState(partner.vat_number ?? "");
  const [crNumber, setCrNumber] = useState(partner.cr_number ?? "");
  const [address, setAddress] = useState<Address>(partner.address ?? EMPTY_ADDRESS);
  const [error, setError] = useState<string | null>(null);

  const updateMutation = useMutation({
    mutationFn: () =>
      identityApi.updatePartner(companyId, partner.id, {
        name,
        name_ar: nameAr || null,
        is_customer: isCustomer,
        is_vendor: isVendor,
        vat_number: vatNumber || null,
        cr_number: crNumber || null,
        address:
          address.street || address.city || address.region || address.postal_code || address.country_code
            ? address
            : null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["partner", companyId, partner.id] });
      queryClient.invalidateQueries({ queryKey: ["partners", companyId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  const backHref = partner.is_vendor && !partner.is_customer ? "/master-data/vendors" : "/master-data/customers";

  return (
    <RecordCard
      breadcrumbs={[{ label: t("nav.master_data") }, { label: partner.name }]}
      name={partner.name}
      code={partner.vat_number ?? undefined}
      statusBadge={
        <div className="flex gap-1">
          {partner.is_customer && <Badge>{t("master_data.partners.is_customer")}</Badge>}
          {partner.is_vendor && <Badge variant="secondary">{t("master_data.partners.is_vendor")}</Badge>}
          <Badge variant={partner.is_active ? "outline" : "destructive"}>
            {partner.is_active ? t("common.active") : t("common.inactive")}
          </Badge>
        </div>
      }
      tabs={[
        {
          key: "overview",
          label: t("master_data.record_card.overview"),
          content: (
            <div className="space-y-4">
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

              <div className="space-y-2 rounded-md border p-3">
                <p className="text-sm font-medium">{t("master_data.partners.address")}</p>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label className="text-xs">{t("master_data.address.street")}</Label>
                    <Input value={address.street ?? ""} onChange={(e) => setAddress((a) => ({ ...a, street: e.target.value }))} />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">{t("master_data.address.city")}</Label>
                    <Input value={address.city ?? ""} onChange={(e) => setAddress((a) => ({ ...a, city: e.target.value }))} />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">{t("master_data.address.region")}</Label>
                    <Input value={address.region ?? ""} onChange={(e) => setAddress((a) => ({ ...a, region: e.target.value }))} />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">{t("master_data.address.postal_code")}</Label>
                    <Input value={address.postal_code ?? ""} onChange={(e) => setAddress((a) => ({ ...a, postal_code: e.target.value }))} />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">{t("master_data.address.country_code")}</Label>
                    <Input value={address.country_code ?? ""} onChange={(e) => setAddress((a) => ({ ...a, country_code: e.target.value }))} maxLength={2} />
                  </div>
                </div>
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => router.push(backHref)}>
                  {t("common.cancel")}
                </Button>
                <Button
                  onClick={() => {
                    setError(null);
                    updateMutation.mutate();
                  }}
                  disabled={updateMutation.isPending || !name || (!isCustomer && !isVendor)}
                >
                  {updateMutation.isPending ? t("common.loading") : t("common.save")}
                </Button>
              </div>
            </div>
          ),
        },
      ]}
    />
  );
}
