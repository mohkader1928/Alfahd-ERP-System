"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Stepper } from "@/components/ui/stepper";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n/config";
import { ApiError } from "@/lib/api-client";
import { toastSuccess } from "@/lib/toast";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { companySetupApi } from "@/features/company-setup/api/client";
import type {
  ApprovalRigor,
  BlueprintDecision,
  CompanyProfile,
  CompanyProfileWriteInput,
  ConfigurationPlan,
  ErpBlueprint,
  SizingResult,
} from "@/features/company-setup/api/types";

const DIMENSION_LABEL_KEYS: Record<string, string> = {
  organizational_complexity: "company_setup.dimension.organizational_complexity",
  transaction_volume: "company_setup.dimension.transaction_volume",
  inventory_complexity: "company_setup.dimension.inventory_complexity",
  financial_complexity: "company_setup.dimension.financial_complexity",
  tax_compliance_complexity: "company_setup.dimension.tax_compliance_complexity",
  asset_complexity: "company_setup.dimension.asset_complexity",
  approval_governance_complexity: "company_setup.dimension.approval_governance_complexity",
  security_access_complexity: "company_setup.dimension.security_access_complexity",
};

const CATEGORY_BADGE_VARIANT: Record<string, "default" | "secondary" | "outline" | "warning"> = {
  STANDARD: "secondary",
  CONFIGURABLE: "default",
  EXTENSIBLE: "warning",
  CUSTOM_DEVELOPMENT: "outline",
};

const initialProfile: CompanyProfileWriteInput = {
  industry: "",
  employee_count: null,
  branch_count: null,
  warehouse_count: null,
  cost_center_tracking_needed: false,
  is_service_business: false,
  monthly_sales_order_volume: null,
  monthly_purchase_order_volume: null,
  desired_user_count: null,
  approval_rigor_preference: "low",
  owns_fixed_assets: false,
  multi_currency_requested: false,
  growth_notes: {},
};

export default function CompanySetupWizardPage() {
  const { t } = useI18n();
  const setActiveCompany = useAuthStore((s) => s.setActiveCompany);
  const setTokens = useAuthStore((s) => s.setTokens);
  const currentCompanyId = useAuthStore((s) => s.activeCompanyId)!;

  // First-Company Entry Integration: /setup's bootstrap success now signs
  // the admin in and lands here with ?mode=first -- the active company IS
  // the one just created (via bootstrap, not this wizard's own Step 0), so
  // there is nothing left to create. Skip straight to Define Profile
  // instead of rendering a redundant "create a company" step for a company
  // that already exists. The ordinary entry (typing /company-setup while
  // already inside an existing company, to add another one) is unaffected
  // -- it still starts at step 0 exactly as before.
  const searchParams = useSearchParams();
  const isFirstCompanyOnboarding = searchParams.get("mode") === "first";

  const [step, setStep] = useState(isFirstCompanyOnboarding ? 1 : 0);
  const [error, setError] = useState<string | null>(null);

  // Accumulated wizard state -- Backend is the sole source of truth for
  // every computed value (sizing, blueprint decisions, plan items); this
  // component only threads the ids/results it already received forward.
  const [newCompanyId, setNewCompanyId] = useState<string | null>(
    isFirstCompanyOnboarding ? currentCompanyId : null
  );
  const [companyForm, setCompanyForm] = useState({ legal_name: "", legal_name_ar: "", vat_number: "" });
  const [profileForm, setProfileForm] = useState<CompanyProfileWriteInput>(initialProfile);
  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [sizing, setSizing] = useState<SizingResult | null>(null);
  const [blueprint, setBlueprint] = useState<ErpBlueprint | null>(null);
  const [plan, setPlan] = useState<ConfigurationPlan | null>(null);
  const [beforeThreshold, setBeforeThreshold] = useState<string | null>(null);

  const steps = [
    t("company_setup.step.create_company"),
    t("company_setup.step.define_profile"),
    t("company_setup.step.review_profile"),
    t("company_setup.step.sizing"),
    t("company_setup.step.generate_blueprint"),
    t("company_setup.step.review_blueprint"),
    t("company_setup.step.approve"),
    t("company_setup.step.review_plan"),
    t("company_setup.step.validate"),
    t("company_setup.step.apply"),
    t("company_setup.step.complete"),
  ].map((label) => ({ label }));

  function fail(err: unknown) {
    setError(err instanceof ApiError ? err.detail : t("common.error"));
  }

  // --- Step 0: Create Company ---
  const createCompanyMutation = useMutation({
    mutationFn: async () => {
      const company = await identityApi.createCompany(currentCompanyId, {
        legal_name: companyForm.legal_name,
        legal_name_ar: companyForm.legal_name_ar,
        vat_number: companyForm.vat_number,
      });
      // authorized_companies is baked into the access token at issue time
      // -- the new company_id isn't in it yet, so every call scoped to it
      // would 403 until a fresh token is minted (see identityApi.refreshToken).
      const currentRefreshToken = useAuthStore.getState().refreshToken;
      if (!currentRefreshToken) throw new Error("No refresh token available");
      const tokens = await identityApi.refreshToken(currentRefreshToken);
      setTokens(tokens.access_token, tokens.refresh_token);
      setActiveCompany(company.id, null);
      return company;
    },
    onSuccess: (company) => {
      setNewCompanyId(company.id);
      setError(null);
      setStep(1);
    },
    onError: fail,
  });

  // --- Step 1: Define Profile ---
  const createProfileMutation = useMutation({
    mutationFn: () => companySetupApi.createProfile(newCompanyId!, profileForm),
    onSuccess: (result) => {
      setProfile(result);
      setError(null);
      setStep(2);
    },
    onError: fail,
  });

  // --- Step 3: Sizing ---
  const sizingMutation = useMutation({
    mutationFn: () => companySetupApi.computeSizing(newCompanyId!),
    onSuccess: (result) => {
      // Deliberately does NOT auto-advance -- the whole point of this step
      // is for the user to actually see the per-dimension breakdown and
      // reasons before moving on, not just a pass-through screen.
      setSizing(result);
      setError(null);
    },
    onError: fail,
  });

  // --- Step 4: Generate Blueprint ---
  const blueprintMutation = useMutation({
    mutationFn: () => companySetupApi.generateBlueprint(newCompanyId!),
    onSuccess: (result) => {
      setBlueprint(result);
      setError(null);
      setStep(5);
    },
    onError: fail,
  });

  // --- Step 6: Approve ---
  const approveMutation = useMutation({
    mutationFn: () => companySetupApi.approveBlueprint(newCompanyId!, blueprint!.id),
    onSuccess: async (result) => {
      setBlueprint(result);
      setError(null);
      try {
        const company = await identityApi.getCompany(newCompanyId!);
        setBeforeThreshold(company.po_approval_threshold);
      } catch {
        setBeforeThreshold(null);
      }
      setStep(7);
    },
    onError: fail,
  });

  // --- Step 7: Create Configuration Plan ---
  const createPlanMutation = useMutation({
    mutationFn: () => companySetupApi.createConfigurationPlan(newCompanyId!),
    onSuccess: (result) => {
      setPlan(result);
      setError(null);
    },
    onError: fail,
  });

  // --- Step 8: Validate ---
  const validateMutation = useMutation({
    mutationFn: () => companySetupApi.validateConfigurationPlan(newCompanyId!, plan!.id),
    onSuccess: (result) => {
      setPlan(result);
      setError(null);
      if (result.status === "validated") setStep(9);
    },
    onError: fail,
  });

  // --- Step 9: Apply ---
  const applyMutation = useMutation({
    mutationFn: () => companySetupApi.applyConfigurationPlan(newCompanyId!, plan!.id),
    onSuccess: (result) => {
      setPlan(result);
      setError(null);
      if (result.status === "applied") {
        toastSuccess(t("toast.success_title"), t("company_setup.apply.success"));
        setStep(10);
      }
    },
    onError: fail,
  });

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t("company_setup.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("company_setup.subtitle")}</p>
      </div>

      <Stepper steps={steps} currentIndex={step} />

      {error && (
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      {step === 0 && (
        <StepCreateCompany
          form={companyForm}
          setForm={setCompanyForm}
          onSubmit={() => {
            setError(null);
            createCompanyMutation.mutate();
          }}
          isPending={createCompanyMutation.isPending}
        />
      )}

      {step === 1 && (
        <StepDefineProfile
          form={profileForm}
          setForm={setProfileForm}
          onSubmit={() => {
            setError(null);
            createProfileMutation.mutate();
          }}
          isPending={createProfileMutation.isPending}
        />
      )}

      {step === 2 && profile && <StepReviewProfile profile={profile} onNext={() => setStep(3)} />}

      {step === 3 && (
        <StepSizing
          sizing={sizing}
          onCompute={() => {
            setError(null);
            sizingMutation.mutate();
          }}
          isPending={sizingMutation.isPending}
          onNext={() => setStep(4)}
        />
      )}

      {step === 4 && (
        <StepGenerateBlueprint
          onGenerate={() => {
            setError(null);
            blueprintMutation.mutate();
          }}
          isPending={blueprintMutation.isPending}
        />
      )}

      {step === 5 && blueprint && <StepReviewBlueprint blueprint={blueprint} onNext={() => setStep(6)} />}

      {step === 6 && blueprint && (
        <StepApprove
          blueprint={blueprint}
          onApprove={() => {
            setError(null);
            approveMutation.mutate();
          }}
          isPending={approveMutation.isPending}
        />
      )}

      {step === 7 && (
        <StepReviewPlan
          plan={plan}
          onCreatePlan={() => {
            setError(null);
            createPlanMutation.mutate();
          }}
          isPending={createPlanMutation.isPending}
          onNext={() => setStep(8)}
        />
      )}

      {step === 8 && plan && (
        <StepValidate
          plan={plan}
          onValidate={() => {
            setError(null);
            validateMutation.mutate();
          }}
          isPending={validateMutation.isPending}
        />
      )}

      {step === 9 && plan && (
        <StepApply
          plan={plan}
          onApply={() => {
            setError(null);
            applyMutation.mutate();
          }}
          isPending={applyMutation.isPending}
        />
      )}

      {step === 10 && plan && (
        <StepComplete plan={plan} beforeThreshold={beforeThreshold} companyName={companyForm.legal_name} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------

function StepCreateCompany({
  form,
  setForm,
  onSubmit,
  isPending,
}: {
  form: { legal_name: string; legal_name_ar: string; vat_number: string };
  setForm: (f: { legal_name: string; legal_name_ar: string; vat_number: string }) => void;
  onSubmit: () => void;
  isPending: boolean;
}) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("company_setup.step.create_company")}</CardTitle>
        <CardDescription>{t("company_setup.create_company.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-1">
            <Label>{t("setup.company_name")}</Label>
            <Input value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label>{t("setup.company_name_ar")}</Label>
            <Input
              value={form.legal_name_ar}
              onChange={(e) => setForm({ ...form, legal_name_ar: e.target.value })}
              dir="rtl"
            />
          </div>
        </div>
        <div className="space-y-1">
          <Label>{t("setup.vat_number")}</Label>
          <Input
            value={form.vat_number}
            onChange={(e) => setForm({ ...form, vat_number: e.target.value })}
            maxLength={15}
            className="max-w-xs"
          />
        </div>
        <Button
          onClick={onSubmit}
          disabled={isPending || !form.legal_name || !form.legal_name_ar || form.vat_number.length !== 15}
        >
          {isPending ? t("common.loading") : t("company_setup.action.create_company")}
        </Button>
      </CardContent>
    </Card>
  );
}

function StepDefineProfile({
  form,
  setForm,
  onSubmit,
  isPending,
}: {
  form: CompanyProfileWriteInput;
  setForm: (f: CompanyProfileWriteInput) => void;
  onSubmit: () => void;
  isPending: boolean;
}) {
  const { t } = useI18n();
  function num(v: string): number | null {
    return v === "" ? null : Number(v);
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("company_setup.step.define_profile")}</CardTitle>
        <CardDescription>{t("company_setup.define_profile.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1">
          <Label>{t("company_setup.profile.industry")}</Label>
          <Input value={form.industry ?? ""} onChange={(e) => setForm({ ...form, industry: e.target.value })} />
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div className="space-y-1">
            <Label>{t("company_setup.profile.employee_count")}</Label>
            <Input
              type="number"
              min="0"
              value={form.employee_count ?? ""}
              onChange={(e) => setForm({ ...form, employee_count: num(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label>{t("company_setup.profile.branch_count")}</Label>
            <Input
              type="number"
              min="0"
              value={form.branch_count ?? ""}
              onChange={(e) => setForm({ ...form, branch_count: num(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label>{t("company_setup.profile.warehouse_count")}</Label>
            <Input
              type="number"
              min="0"
              value={form.warehouse_count ?? ""}
              onChange={(e) => setForm({ ...form, warehouse_count: num(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label>{t("company_setup.profile.monthly_sales_order_volume")}</Label>
            <Input
              type="number"
              min="0"
              value={form.monthly_sales_order_volume ?? ""}
              onChange={(e) => setForm({ ...form, monthly_sales_order_volume: num(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label>{t("company_setup.profile.monthly_purchase_order_volume")}</Label>
            <Input
              type="number"
              min="0"
              value={form.monthly_purchase_order_volume ?? ""}
              onChange={(e) => setForm({ ...form, monthly_purchase_order_volume: num(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label>{t("company_setup.profile.desired_user_count")}</Label>
            <Input
              type="number"
              min="0"
              value={form.desired_user_count ?? ""}
              onChange={(e) => setForm({ ...form, desired_user_count: num(e.target.value) })}
            />
          </div>
        </div>

        <div className="space-y-1">
          <Label>{t("company_setup.profile.approval_rigor")}</Label>
          <Select
            value={form.approval_rigor_preference ?? "low"}
            onValueChange={(v) => v && setForm({ ...form, approval_rigor_preference: v as ApprovalRigor })}
          >
            <SelectTrigger className="max-w-xs">
              <SelectValue>{(value: string) => t(`company_setup.approval_rigor.${value}`)}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="low">{t("company_setup.approval_rigor.low")}</SelectItem>
              <SelectItem value="medium">{t("company_setup.approval_rigor.medium")}</SelectItem>
              <SelectItem value="high">{t("company_setup.approval_rigor.high")}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={!!form.is_service_business}
              onChange={(e) => setForm({ ...form, is_service_business: e.target.checked })}
            />
            {t("company_setup.profile.is_service_business")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={!!form.cost_center_tracking_needed}
              onChange={(e) => setForm({ ...form, cost_center_tracking_needed: e.target.checked })}
            />
            {t("company_setup.profile.cost_center_tracking_needed")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={!!form.owns_fixed_assets}
              onChange={(e) => setForm({ ...form, owns_fixed_assets: e.target.checked })}
            />
            {t("company_setup.profile.owns_fixed_assets")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={!!form.multi_currency_requested}
              onChange={(e) => setForm({ ...form, multi_currency_requested: e.target.checked })}
            />
            {t("company_setup.profile.multi_currency_requested")}
          </label>
        </div>

        <div className="space-y-1">
          <Label>{t("company_setup.profile.growth_notes")}</Label>
          <Textarea
            placeholder={t("company_setup.profile.growth_notes_placeholder")}
            value={(form.growth_notes?.notes as string) ?? ""}
            onChange={(e) => setForm({ ...form, growth_notes: { notes: e.target.value } })}
          />
        </div>

        <p className="text-xs text-muted-foreground">{t("company_setup.profile.capability_gap_note")}</p>

        <Button onClick={onSubmit} disabled={isPending}>
          {isPending ? t("common.loading") : t("company_setup.action.save_profile")}
        </Button>
      </CardContent>
    </Card>
  );
}

function StepReviewProfile({ profile, onNext }: { profile: CompanyProfile; onNext: () => void }) {
  const { t } = useI18n();
  const rows: [string, string | number | null][] = [
    [t("company_setup.profile.industry"), profile.industry],
    [t("company_setup.profile.employee_count"), profile.employee_count],
    [t("company_setup.profile.branch_count"), profile.branch_count],
    [t("company_setup.profile.warehouse_count"), profile.warehouse_count],
    [t("company_setup.profile.approval_rigor"), t(`company_setup.approval_rigor.${profile.approval_rigor_preference}`)],
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("company_setup.step.review_profile")}</CardTitle>
        <CardDescription>{t("company_setup.review_profile.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <dl className="grid grid-cols-2 gap-3 text-sm">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="font-medium">{value ?? "—"}</dd>
            </div>
          ))}
        </dl>
        <Button onClick={onNext}>{t("company_setup.action.continue_to_sizing")}</Button>
      </CardContent>
    </Card>
  );
}

function StepSizing({
  sizing,
  onCompute,
  isPending,
  onNext,
}: {
  sizing: SizingResult | null;
  onCompute: () => void;
  isPending: boolean;
  onNext: () => void;
}) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("company_setup.step.sizing")}</CardTitle>
        <CardDescription>{t("company_setup.sizing.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!sizing && (
          <Button onClick={onCompute} disabled={isPending}>
            {isPending ? t("common.loading") : t("company_setup.action.compute_sizing")}
          </Button>
        )}
        {sizing && (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              {t("company_setup.sizing.rule_version")}: {sizing.rule_version}
            </p>
            {Object.entries(sizing.dimension_scores).map(([key, dim]) => (
              <div key={key} className="rounded-md border p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{t(DIMENSION_LABEL_KEYS[key] ?? key)}</span>
                  <Badge variant={dim.score >= 60 ? "warning" : "secondary"}>{dim.score}/100</Badge>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{dim.reason}</p>
              </div>
            ))}
            <Button onClick={onNext}>{t("company_setup.action.continue_to_blueprint")}</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function StepGenerateBlueprint({ onGenerate, isPending }: { onGenerate: () => void; isPending: boolean }) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("company_setup.step.generate_blueprint")}</CardTitle>
        <CardDescription>{t("company_setup.generate_blueprint.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <Button onClick={onGenerate} disabled={isPending}>
          {isPending ? t("common.loading") : t("company_setup.action.generate_blueprint")}
        </Button>
      </CardContent>
    </Card>
  );
}

function DecisionRow({ decision }: { decision: BlueprintDecision }) {
  const { t } = useI18n();
  return (
    <div className="rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{decision.key}</span>
        <Badge variant={CATEGORY_BADGE_VARIANT[decision.category] ?? "outline"}>{decision.category}</Badge>
        {decision.actionable ? (
          <Badge variant="secondary">{t("company_setup.blueprint.actionable")}</Badge>
        ) : (
          <Badge variant="outline">{t("company_setup.blueprint.capability_gap")}</Badge>
        )}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{decision.reason}</p>
    </div>
  );
}

function StepReviewBlueprint({ blueprint, onNext }: { blueprint: ErpBlueprint; onNext: () => void }) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("company_setup.step.review_blueprint")}</CardTitle>
        <CardDescription>
          {t("company_setup.review_blueprint.description")} ({t("company_setup.blueprint.version")}{" "}
          {blueprint.blueprint_version})
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {blueprint.decisions.map((d) => (
          <DecisionRow key={d.key} decision={d} />
        ))}
        <Button onClick={onNext}>{t("company_setup.action.continue_to_approve")}</Button>
      </CardContent>
    </Card>
  );
}

function StepApprove({
  blueprint,
  onApprove,
  isPending,
}: {
  blueprint: ErpBlueprint;
  onApprove: () => void;
  isPending: boolean;
}) {
  const { t } = useI18n();
  if (blueprint.status === "approved") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("company_setup.step.approve")}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{t("company_setup.approve.already_approved")}</p>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("company_setup.step.approve")}</CardTitle>
        <CardDescription>{t("company_setup.approve.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <Button onClick={onApprove} disabled={isPending}>
          {isPending ? t("common.loading") : t("company_setup.action.approve_blueprint")}
        </Button>
      </CardContent>
    </Card>
  );
}

function StepReviewPlan({
  plan,
  onCreatePlan,
  isPending,
  onNext,
}: {
  plan: ConfigurationPlan | null;
  onCreatePlan: () => void;
  isPending: boolean;
  onNext: () => void;
}) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("company_setup.step.review_plan")}</CardTitle>
        <CardDescription>{t("company_setup.review_plan.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!plan && (
          <Button onClick={onCreatePlan} disabled={isPending}>
            {isPending ? t("common.loading") : t("company_setup.action.create_plan")}
          </Button>
        )}
        {plan && (
          <div className="space-y-3">
            <div>
              <p className="text-sm font-medium">{t("company_setup.plan.will_apply")}</p>
              <ul className="mt-1 list-inside list-disc text-sm text-muted-foreground">
                {plan.items.map((item) => (
                  <li key={item.id}>{item.decision_key}</li>
                ))}
              </ul>
            </div>
            <Separator />
            <p className="text-xs text-muted-foreground">{t("company_setup.plan.gap_note")}</p>
            <Button onClick={onNext}>{t("company_setup.action.continue_to_validate")}</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function StepValidate({
  plan,
  onValidate,
  isPending,
}: {
  plan: ConfigurationPlan;
  onValidate: () => void;
  isPending: boolean;
}) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("company_setup.step.validate")}</CardTitle>
        <CardDescription>{t("company_setup.validate.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm">
          {t("company_setup.plan.status")}: <Badge>{plan.status}</Badge>
        </p>
        {plan.status === "draft" && (
          <Button onClick={onValidate} disabled={isPending}>
            {isPending ? t("common.loading") : t("company_setup.action.validate_plan")}
          </Button>
        )}
        {plan.failure_reason && <p className="text-sm text-destructive">{plan.failure_reason}</p>}
      </CardContent>
    </Card>
  );
}

function StepApply({ plan, onApply, isPending }: { plan: ConfigurationPlan; onApply: () => void; isPending: boolean }) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("company_setup.step.apply")}</CardTitle>
        <CardDescription>{t("company_setup.apply.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button onClick={onApply} disabled={isPending}>
          {isPending ? t("common.loading") : t("company_setup.action.apply_plan")}
        </Button>
        {plan.failure_reason && <p className="text-sm text-destructive">{plan.failure_reason}</p>}
      </CardContent>
    </Card>
  );
}

function StepComplete({
  plan,
  beforeThreshold,
  companyName,
}: {
  plan: ConfigurationPlan;
  beforeThreshold: string | null;
  companyName: string;
}) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("company_setup.step.complete")}</CardTitle>
        <CardDescription>
          {t("company_setup.complete.description")} {companyName}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="text-sm font-medium">{t("company_setup.complete.what_changed")}</p>
          <ul className="mt-1 space-y-1 text-sm text-muted-foreground">
            {plan.items.map((item) => (
              <li key={item.id} className="flex items-center gap-2">
                <Badge variant={item.status === "applied" ? "secondary" : "outline"}>{item.status}</Badge>
                {item.decision_key}
              </li>
            ))}
          </ul>
        </div>
        <Separator />
        <p className="text-xs text-muted-foreground">
          {t("company_setup.complete.before")}: {beforeThreshold ?? "—"}
        </p>
        <Button nativeButton={false} render={<Link href="/company-setup/assessment" />}>
          {t("company_setup.action.view_assessment")}
        </Button>
      </CardContent>
    </Card>
  );
}
