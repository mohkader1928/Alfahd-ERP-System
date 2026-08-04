"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RecordCard } from "@/components/erp/record-card/record-card";
import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { EntityImageUpload } from "@/components/erp/entity-image/entity-image-upload";
import { Can } from "@/components/erp/permissions/can";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ErrorState } from "@/components/erp/states/error-state";
import { NotFoundState } from "@/components/erp/states/not-found";
import { EmptyState } from "@/components/erp/states/empty-state";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { ApiError } from "@/lib/api-client";
import { toastError, toastSuccess } from "@/lib/toast";
import type { Partner, PartnerAddress } from "@/features/identity/api/types";

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

  return <PartnerProfile key={partnerQuery.data.id} partner={partnerQuery.data} companyId={companyId} />;
}

function PartnerProfile({ partner, companyId }: { partner: Partner; companyId: string }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();

  const [name, setName] = useState(partner.name);
  const [nameAr, setNameAr] = useState(partner.name_ar ?? "");
  const [isCompany, setIsCompany] = useState(partner.is_company);
  const [isCustomer, setIsCustomer] = useState(partner.is_customer);
  const [isVendor, setIsVendor] = useState(partner.is_vendor);
  const [isEmployee, setIsEmployee] = useState(partner.is_employee);
  const [jobTitle, setJobTitle] = useState(partner.job_title ?? "");
  const [isPrimaryContact, setIsPrimaryContact] = useState(partner.is_primary_contact);
  const [phone, setPhone] = useState(partner.phone ?? "");
  const [mobile, setMobile] = useState(partner.mobile ?? "");
  const [email, setEmail] = useState(partner.email ?? "");
  const [website, setWebsite] = useState(partner.website ?? "");
  const [vatNumber, setVatNumber] = useState(partner.vat_number ?? "");
  const [crNumber, setCrNumber] = useState(partner.cr_number ?? "");
  const [error, setError] = useState<string | null>(null);

  const invalidatePartner = () => {
    queryClient.invalidateQueries({ queryKey: ["partner", companyId, partner.id] });
    queryClient.invalidateQueries({ queryKey: ["partners", companyId] });
  };

  const updateMutation = useMutation({
    mutationFn: () =>
      identityApi.updatePartner(companyId, partner.id, {
        name,
        name_ar: nameAr || null,
        is_company: isCompany,
        is_customer: isCustomer,
        is_vendor: isVendor,
        is_employee: isEmployee,
        job_title: jobTitle || null,
        is_primary_contact: isPrimaryContact,
        phone: phone || null,
        mobile: mobile || null,
        email: email || null,
        website: website || null,
        vat_number: vatNumber || null,
        cr_number: crNumber || null,
        address: partner.address,
      }),
    onSuccess: () => {
      invalidatePartner();
      toastSuccess(t("toast.success_title"), t("common.save"));
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  const uploadImageMutation = useMutation({
    mutationFn: (file: File) => identityApi.uploadPartnerImage(companyId, partner.id, file),
    onSuccess: () => {
      invalidatePartner();
      toastSuccess(t("toast.success_title"), t("media.upload"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  const removeImageMutation = useMutation({
    mutationFn: () => identityApi.deletePartnerImage(companyId, partner.id),
    onSuccess: () => {
      invalidatePartner();
      toastSuccess(t("toast.success_title"), t("media.remove"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  const archiveMutation = useMutation({
    mutationFn: () => (partner.is_active ? identityApi.archivePartner(companyId, partner.id) : identityApi.restorePartner(companyId, partner.id)),
    onSuccess: () => {
      invalidatePartner();
      toastSuccess(t("toast.success_title"), partner.is_active ? t("master_data.partners.archived") : t("master_data.partners.restored"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  const parentQuery = useQuery({
    queryKey: ["partner", companyId, partner.parent_partner_id],
    queryFn: () => identityApi.getPartner(companyId, partner.parent_partner_id!),
    enabled: !!partner.parent_partner_id,
  });

  return (
    <RecordCard
      breadcrumbs={[{ label: t("nav.master_data") }, { label: t("master_data.address_book.title"), href: "/master-data/address-book" }, { label: partner.name }]}
      name={partner.name}
      code={partner.vat_number ?? undefined}
      avatar={<EntityImage src={partner.image_path} name={partner.name} size="md" />}
      statusBadge={
        <div className="flex gap-1">
          {partner.is_customer && <Badge>{t("master_data.partners.is_customer")}</Badge>}
          {partner.is_vendor && <Badge variant="secondary">{t("master_data.partners.is_vendor")}</Badge>}
          {partner.is_employee && <Badge variant="secondary">{t("master_data.partners.is_employee")}</Badge>}
          <Badge variant={partner.is_active ? "outline" : "destructive"}>
            {partner.is_active ? t("common.active") : t("common.inactive")}
          </Badge>
        </div>
      }
      primaryActions={
        <Can permission="partner.update">
          <Button variant="outline" size="sm" onClick={() => archiveMutation.mutate()} disabled={archiveMutation.isPending}>
            {partner.is_active ? t("master_data.partners.archive") : t("master_data.partners.restore")}
          </Button>
          <Button
            size="sm"
            onClick={() => {
              setError(null);
              updateMutation.mutate();
            }}
            disabled={updateMutation.isPending || !name}
          >
            {updateMutation.isPending ? t("common.loading") : t("common.save")}
          </Button>
        </Can>
      }
      tabs={[
        {
          key: "overview",
          label: t("master_data.record_card.overview"),
          content: (
            <div className="space-y-4">
              <div className="space-y-1">
                <Label>{t("master_data.partners.image")}</Label>
                <Can permission="partner.update">
                  <EntityImageUpload
                    src={partner.image_path}
                    name={partner.name}
                    isUploading={uploadImageMutation.isPending}
                    isRemoving={removeImageMutation.isPending}
                    onUpload={(file) => uploadImageMutation.mutate(file)}
                    onRemove={partner.image_path ? () => removeImageMutation.mutate() : undefined}
                  />
                </Can>
              </div>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <input type="radio" checked={isCompany} onChange={() => setIsCompany(true)} />
                  {t("master_data.partners.filter_company")}
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="radio" checked={!isCompany} onChange={() => setIsCompany(false)} />
                  {t("master_data.partners.filter_individual")}
                </label>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label>{t("master_data.partners.name")}</Label>
                  <Input value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label>{t("master_data.partners.name_ar")}</Label>
                  <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} dir="rtl" />
                </div>
              </div>
              {partner.parent_partner_id && parentQuery.data && (
                <div className="rounded-md border p-3 text-sm">
                  <p className="text-muted-foreground">{t("master_data.partners.contact_of")}</p>
                  <Link href={`/master-data/partners/${parentQuery.data.id}`} className="font-medium underline-offset-4 hover:underline">
                    {parentQuery.data.name}
                  </Link>
                </div>
              )}
              {error && <p className="text-sm text-destructive">{error}</p>}
            </div>
          ),
        },
        {
          key: "contact",
          label: t("master_data.partners.tab_contact_info"),
          content: (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1">
                <Label>{t("master_data.partners.phone")}</Label>
                <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>{t("master_data.partners.mobile")}</Label>
                <Input value={mobile} onChange={(e) => setMobile(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>{t("master_data.partners.email")}</Label>
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>{t("master_data.partners.website")}</Label>
                <Input value={website} onChange={(e) => setWebsite(e.target.value)} />
              </div>
            </div>
          ),
        },
        {
          key: "addresses",
          label: t("master_data.partners.tab_addresses"),
          content: <AddressesTab companyId={companyId} partnerId={partner.id} />,
        },
        {
          key: "contacts",
          label: t("master_data.partners.tab_contacts"),
          content: isCompany ? (
            <ContactsTab companyId={companyId} parentPartner={partner} />
          ) : (
            <p className="text-sm text-muted-foreground">{t("master_data.partners.contacts_company_only")}</p>
          ),
        },
        {
          key: "roles",
          label: t("master_data.partners.tab_roles"),
          content: (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-4">
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
              {partner.parent_partner_id && (
                <div className="grid grid-cols-1 gap-4 border-t pt-4 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label>{t("master_data.partners.job_title")}</Label>
                    <Input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
                  </div>
                  <label className="flex items-center gap-2 self-end pb-2 text-sm">
                    <input type="checkbox" checked={isPrimaryContact} onChange={(e) => setIsPrimaryContact(e.target.checked)} />
                    {t("master_data.partners.is_primary_contact")}
                  </label>
                </div>
              )}
            </div>
          ),
        },
        {
          key: "tax",
          label: t("master_data.partners.tab_tax_legal"),
          content: (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1">
                <Label>{t("master_data.partners.vat_number")}</Label>
                <Input value={vatNumber} onChange={(e) => setVatNumber(e.target.value)} maxLength={15} />
              </div>
              <div className="space-y-1">
                <Label>{t("master_data.partners.cr_number")}</Label>
                <Input value={crNumber} onChange={(e) => setCrNumber(e.target.value)} />
              </div>
            </div>
          ),
        },
        {
          key: "accounting",
          label: t("master_data.partners.tab_accounting"),
          content: (
            <div className="flex flex-wrap gap-2">
              {partner.is_customer && (
                <Button variant="outline" render={<Link href={`/accounting?tab=customer-subledger&partner=${partner.id}`} />}>
                  {t("accounting.tabs.customer_subledger")}
                </Button>
              )}
              {partner.is_vendor && (
                <Button variant="outline" render={<Link href={`/accounting?tab=vendor-subledger&partner=${partner.id}`} />}>
                  {t("accounting.tabs.vendor_subledger")}
                </Button>
              )}
              {!partner.is_customer && !partner.is_vendor && (
                <p className="text-sm text-muted-foreground">{t("master_data.partners.accounting_no_roles")}</p>
              )}
            </div>
          ),
        },
        {
          key: "related",
          label: t("master_data.partners.tab_related"),
          content: partner.parent_partner_id && parentQuery.data ? (
            <div className="text-sm">
              <p className="text-muted-foreground">{t("master_data.partners.contact_of")}</p>
              <Link href={`/master-data/partners/${parentQuery.data.id}`} className="font-medium underline-offset-4 hover:underline">
                {parentQuery.data.name}
              </Link>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t("master_data.partners.no_related_records")}</p>
          ),
        },
      ]}
    />
  );
}

const ADDRESS_TYPES: PartnerAddress["type"][] = ["billing", "shipping", "other"];

function AddressesTab({ companyId, partnerId }: { companyId: string; partnerId: string }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<PartnerAddress | null>(null);
  const [type, setType] = useState<PartnerAddress["type"]>("billing");
  const [isDefault, setIsDefault] = useState(false);
  const [street, setStreet] = useState("");
  const [city, setCity] = useState("");
  const [region, setRegion] = useState("");
  const [postalCode, setPostalCode] = useState("");
  const [countryCode, setCountryCode] = useState("");

  const addressesQuery = useQuery({
    queryKey: ["partner-addresses", companyId, partnerId],
    queryFn: () => identityApi.listPartnerAddresses(companyId, partnerId),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["partner-addresses", companyId, partnerId] });

  function resetForm() {
    setEditing(null);
    setType("billing");
    setIsDefault(false);
    setStreet("");
    setCity("");
    setRegion("");
    setPostalCode("");
    setCountryCode("");
    setShowForm(false);
  }

  function startEdit(a: PartnerAddress) {
    setEditing(a);
    setType(a.type);
    setIsDefault(a.is_default);
    setStreet(a.street ?? "");
    setCity(a.city ?? "");
    setRegion(a.region ?? "");
    setPostalCode(a.postal_code ?? "");
    setCountryCode(a.country_code ?? "");
    setShowForm(true);
  }

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = { type, is_default: isDefault, street: street || null, city: city || null, region: region || null, postal_code: postalCode || null, country_code: countryCode || null };
      return editing
        ? identityApi.updatePartnerAddress(companyId, partnerId, editing.id, payload)
        : identityApi.createPartnerAddress(companyId, partnerId, payload);
    },
    onSuccess: () => {
      invalidate();
      toastSuccess(t("toast.success_title"), t("common.save"));
      resetForm();
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  const deleteMutation = useMutation({
    mutationFn: (a: PartnerAddress) => identityApi.deletePartnerAddress(companyId, partnerId, a.id),
    onSuccess: () => {
      invalidate();
      toastSuccess(t("toast.success_title"), t("common.delete"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  const typeLabel = (ty: PartnerAddress["type"]) =>
    ({ billing: t("master_data.partners.address_billing"), shipping: t("master_data.partners.address_shipping"), other: t("master_data.partners.address_other") })[ty];

  return (
    <div className="space-y-3">
      {addressesQuery.isLoading && <p className="text-sm text-muted-foreground">{t("common.loading")}</p>}
      {!addressesQuery.isLoading && (addressesQuery.data?.length ?? 0) === 0 && !showForm && (
        <EmptyState title={t("master_data.partners.no_addresses")} />
      )}
      <div className="space-y-2">
        {addressesQuery.data?.map((a) => (
          <div key={a.id} className="flex items-center justify-between rounded-md border p-3 text-sm">
            <div>
              <div className="flex items-center gap-2">
                <span className="font-medium">{typeLabel(a.type)}</span>
                {a.is_default && <Badge variant="outline">{t("master_data.partners.address_default")}</Badge>}
              </div>
              <p className="text-muted-foreground">
                {[a.street, a.city, a.region, a.postal_code, a.country_code].filter(Boolean).join(", ") || "—"}
              </p>
            </div>
            <Can permission="partner.update">
              <div className="flex gap-2">
                <Button variant="ghost" size="xs" onClick={() => startEdit(a)}>
                  {t("common.edit")}
                </Button>
                <Button variant="ghost" size="xs" onClick={() => deleteMutation.mutate(a)} disabled={deleteMutation.isPending}>
                  {t("common.delete")}
                </Button>
              </div>
            </Can>
          </div>
        ))}
      </div>

      {showForm ? (
        <div className="space-y-3 rounded-md border p-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label className="text-xs">{t("master_data.partners.address_type")}</Label>
              <Select value={type} onValueChange={(v) => setType((v as PartnerAddress["type"]) ?? "billing")}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ADDRESS_TYPES.map((ty) => (
                    <SelectItem key={ty} value={ty}>
                      {typeLabel(ty)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <label className="flex items-center gap-2 self-end pb-2 text-sm">
              <input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} />
              {t("master_data.partners.address_default")}
            </label>
            <div className="space-y-1 sm:col-span-2">
              <Label className="text-xs">{t("master_data.address.street")}</Label>
              <Input value={street} onChange={(e) => setStreet(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">{t("master_data.address.city")}</Label>
              <Input value={city} onChange={(e) => setCity(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">{t("master_data.address.region")}</Label>
              <Input value={region} onChange={(e) => setRegion(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">{t("master_data.address.postal_code")}</Label>
              <Input value={postalCode} onChange={(e) => setPostalCode(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">{t("master_data.address.country_code")}</Label>
              <Input value={countryCode} onChange={(e) => setCountryCode(e.target.value)} maxLength={2} />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={resetForm}>
              {t("common.cancel")}
            </Button>
            <Button size="sm" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
              {saveMutation.isPending ? t("common.loading") : t("common.save")}
            </Button>
          </div>
        </div>
      ) : (
        <Can permission="partner.update">
          <Button variant="outline" size="sm" onClick={() => setShowForm(true)}>
            {t("master_data.partners.add_address")}
          </Button>
        </Can>
      )}
    </div>
  );
}

function ContactsTab({ companyId, parentPartner }: { companyId: string; parentPartner: Partner }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const branchId = useAuthStore((s) => s.activeBranchId);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [isPrimary, setIsPrimary] = useState(false);

  const contactsQuery = useQuery({
    queryKey: ["partners", companyId, "contacts-of", parentPartner.id],
    queryFn: () => identityApi.listPartners(companyId, branchId, { parentPartnerId: parentPartner.id, includeArchived: true }),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      identityApi.createPartner(companyId, branchId, {
        name,
        is_company: false,
        parent_partner_id: parentPartner.id,
        job_title: jobTitle || null,
        is_primary_contact: isPrimary,
        email: email || null,
        phone: phone || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["partners", companyId, "contacts-of", parentPartner.id] });
      toastSuccess(t("toast.success_title"), t("master_data.partners.add_contact"));
      setName("");
      setJobTitle("");
      setEmail("");
      setPhone("");
      setIsPrimary(false);
      setShowForm(false);
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  return (
    <div className="space-y-3">
      {contactsQuery.isLoading && <p className="text-sm text-muted-foreground">{t("common.loading")}</p>}
      {!contactsQuery.isLoading && (contactsQuery.data?.length ?? 0) === 0 && !showForm && (
        <EmptyState title={t("master_data.partners.no_contacts")} />
      )}
      <div className="space-y-2">
        {contactsQuery.data?.map((c) => (
          <Link
            key={c.id}
            href={`/master-data/partners/${c.id}`}
            className="flex items-center justify-between rounded-md border p-3 text-sm hover:bg-muted/40"
          >
            <div className="flex items-center gap-2">
              <EntityImage src={c.image_path} name={c.name} size="xs" />
              <div>
                <p className="font-medium">
                  {c.name} {c.is_primary_contact && <Badge variant="outline">{t("master_data.partners.is_primary_contact")}</Badge>}
                </p>
                <p className="text-muted-foreground">{c.job_title ?? "—"}</p>
              </div>
            </div>
            <span className="text-muted-foreground">{c.email ?? c.phone ?? ""}</span>
          </Link>
        ))}
      </div>

      {showForm ? (
        <div className="space-y-3 rounded-md border p-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label className="text-xs">{t("master_data.partners.name")}</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">{t("master_data.partners.job_title")}</Label>
              <Input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">{t("master_data.partners.email")}</Label>
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">{t("master_data.partners.phone")}</Label>
              <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
            </div>
            <label className="flex items-center gap-2 self-end pb-2 text-sm">
              <input type="checkbox" checked={isPrimary} onChange={(e) => setIsPrimary(e.target.checked)} />
              {t("master_data.partners.is_primary_contact")}
            </label>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setShowForm(false)}>
              {t("common.cancel")}
            </Button>
            <Button size="sm" onClick={() => createMutation.mutate()} disabled={createMutation.isPending || !name}>
              {createMutation.isPending ? t("common.loading") : t("common.save")}
            </Button>
          </div>
        </div>
      ) : (
        <Can permission="partner.create">
          <Button variant="outline" size="sm" onClick={() => setShowForm(true)}>
            {t("master_data.partners.add_contact")}
          </Button>
        </Can>
      )}
    </div>
  );
}
