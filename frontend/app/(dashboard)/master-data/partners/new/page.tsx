"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { FormView } from "@/components/erp/form-view/form-view";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { ApiError } from "@/lib/api-client";
import type { Partner } from "@/features/identity/api/types";

const KIND_TO_TITLE_KEY: Record<string, string> = {
  customer: "master_data.customers.new",
  vendor: "master_data.vendors.new",
  employee: "master_data.employees.new",
};
const KIND_TO_BACK: Record<string, string> = {
  customer: "/master-data/customers",
  vendor: "/master-data/vendors",
  employee: "/master-data/employees",
};

function normalize(s: string) {
  return s.trim().toLowerCase();
}

export default function NewPartnerPage() {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialKind = (["customer", "vendor", "employee"].includes(searchParams.get("kind") ?? "")
    ? searchParams.get("kind")
    : "customer") as "customer" | "vendor" | "employee";
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);
  const queryClient = useQueryClient();

  const [isCompany, setIsCompany] = useState(true);
  const [name, setName] = useState("");
  const [nameAr, setNameAr] = useState("");
  const [isCustomer, setIsCustomer] = useState(initialKind === "customer");
  const [isVendor, setIsVendor] = useState(initialKind === "vendor");
  const [isEmployee, setIsEmployee] = useState(initialKind === "employee");
  const [vatNumber, setVatNumber] = useState("");
  const [crNumber, setCrNumber] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Condition 6: smart, non-blocking duplicate warning — checked against
  // this company's own Partner list (already RLS/company-scoped), no new
  // backend endpoint needed.
  const allPartnersQuery = useQuery({
    queryKey: ["partners", companyId, "all", "active"],
    queryFn: () => identityApi.listPartners(companyId, branchId, {}),
  });

  const possibleDuplicates = useMemo(() => {
    const list = allPartnersQuery.data ?? [];
    if (!name.trim() && !vatNumber.trim() && !crNumber.trim() && !email.trim() && !phone.trim()) return [];
    return list.filter((p: Partner) => {
      if (vatNumber.trim() && p.vat_number && normalize(p.vat_number) === normalize(vatNumber)) return true;
      if (crNumber.trim() && p.cr_number && normalize(p.cr_number) === normalize(crNumber)) return true;
      if (email.trim() && p.email && normalize(p.email) === normalize(email)) return true;
      if (phone.trim() && p.phone && normalize(p.phone) === normalize(phone)) return true;
      if (name.trim().length >= 3 && normalize(p.name).includes(normalize(name))) return true;
      return false;
    });
  }, [allPartnersQuery.data, name, vatNumber, crNumber, email, phone]);

  const createMutation = useMutation({
    mutationFn: () =>
      identityApi.createPartner(companyId, branchId, {
        name,
        name_ar: nameAr || null,
        is_company: isCompany,
        is_customer: isCustomer,
        is_vendor: isVendor,
        is_employee: isEmployee,
        vat_number: vatNumber || null,
        cr_number: crNumber || null,
        email: email || null,
        phone: phone || null,
      }),
    onSuccess: (partner) => {
      queryClient.invalidateQueries({ queryKey: ["partners", companyId] });
      router.push(`/master-data/partners/${partner.id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  const backHref = KIND_TO_BACK[initialKind];

  return (
    <FormView
      title={t(KIND_TO_TITLE_KEY[initialKind])}
      breadcrumbs={[
        { label: t("nav.master_data") },
        { label: t(KIND_TO_TITLE_KEY[initialKind].replace(".new", ".title")), href: backHref },
        { label: t("common.new") },
      ]}
      onSave={() => {
        setError(null);
        createMutation.mutate();
      }}
      onCancel={() => router.push(backHref)}
      isSaving={createMutation.isPending}
      saveDisabled={!name}
      error={error}
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex items-center gap-4 sm:col-span-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" checked={isCompany} onChange={() => setIsCompany(true)} />
            {t("master_data.partners.filter_company")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" checked={!isCompany} onChange={() => setIsCompany(false)} />
            {t("master_data.partners.filter_individual")}
          </label>
        </div>
        <div className="space-y-1">
          <Label>{t("master_data.partners.name")}</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label>{t("master_data.partners.name_ar")}</Label>
          <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} dir="rtl" />
        </div>
        <div className="space-y-1">
          <Label>{t("master_data.partners.email")}</Label>
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label>{t("master_data.partners.phone")}</Label>
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
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
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={isEmployee} onChange={(e) => setIsEmployee(e.target.checked)} />
            {t("master_data.partners.is_employee")}
          </label>
        </div>
      </div>

      {possibleDuplicates.length > 0 && (
        <div className="rounded-md border border-amber-400/60 bg-amber-50 p-3 text-sm dark:bg-amber-950/30">
          <p className="font-medium">{t("master_data.partners.possible_duplicate")}</p>
          <ul className="mt-1 space-y-1">
            {possibleDuplicates.slice(0, 5).map((p) => (
              <li key={p.id}>
                <Link href={`/master-data/partners/${p.id}`} className="underline-offset-4 hover:underline" target="_blank">
                  {p.name} {p.vat_number ? `— VAT ${p.vat_number}` : ""}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </FormView>
  );
}
