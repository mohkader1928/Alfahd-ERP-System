"use client";

import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { companySetupApi } from "@/features/company-setup/api/client";
import type { CapabilityMatrixEntry, FutureNeed } from "@/features/company-setup/api/types";

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

const FUTURE_NEED_LABEL_KEYS: Record<string, string> = {
  api_integration_access: "assessment.future_need.api_integration_access",
  ecommerce_connection: "assessment.future_need.ecommerce_connection",
  payroll_hr: "assessment.future_need.payroll_hr",
  manufacturing: "assessment.future_need.manufacturing",
  crm: "assessment.future_need.crm",
};

export default function CustomerAssessmentPage() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["customer-assessment", companyId],
    queryFn: () => companySetupApi.getAssessment(companyId),
  });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">{t("common.loading")}</p>;
  }
  if (isError || !data) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-sm text-muted-foreground">{t("assessment.not_available")}</p>
        </CardContent>
      </Card>
    );
  }

  const actionableItems = data.capability_matrix.filter((e) => e.actionable);
  const gapItems = data.capability_matrix.filter((e) => e.is_gap);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t("assessment.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("assessment.subtitle")}</p>
      </div>

      {/* A. Company Profile */}
      <Card>
        <CardHeader>
          <CardTitle>{t("assessment.section.profile")}</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <ProfileField label={t("company_setup.profile.industry")} value={data.profile.industry} />
            <ProfileField label={t("company_setup.profile.employee_count")} value={data.profile.employee_count} />
            <ProfileField label={t("company_setup.profile.branch_count")} value={data.profile.branch_count} />
            <ProfileField label={t("company_setup.profile.warehouse_count")} value={data.profile.warehouse_count} />
            <ProfileField
              label={t("company_setup.profile.desired_user_count")}
              value={data.profile.desired_user_count}
            />
            <ProfileField
              label={t("company_setup.profile.approval_rigor")}
              value={t(`company_setup.approval_rigor.${data.profile.approval_rigor_preference}`)}
            />
          </dl>
        </CardContent>
      </Card>

      {/* B. Sizing */}
      <Card>
        <CardHeader>
          <CardTitle>{t("assessment.section.sizing")}</CardTitle>
          {!data.sizing && <CardDescription>{t("assessment.sizing.not_yet")}</CardDescription>}
        </CardHeader>
        {data.sizing && (
          <CardContent className="space-y-3">
            <p className="text-xs text-muted-foreground">
              {t("company_setup.sizing.rule_version")}: {data.sizing.rule_version}
            </p>
            {Object.entries(data.sizing.dimension_scores).map(([key, dim]) => (
              <div key={key} className="rounded-md border p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{t(DIMENSION_LABEL_KEYS[key] ?? key)}</span>
                  <Badge variant={dim.score >= 60 ? "warning" : "secondary"}>{dim.score}/100</Badge>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{dim.reason}</p>
              </div>
            ))}
          </CardContent>
        )}
      </Card>

      {/* C/D. ERP Blueprint -- Capability Matrix */}
      <Card>
        <CardHeader>
          <CardTitle>{t("assessment.section.blueprint")}</CardTitle>
          {data.blueprint ? (
            <CardDescription>
              {t("company_setup.blueprint.version")} {data.blueprint.blueprint_version} --{" "}
              {t(`assessment.blueprint_status.${data.blueprint.status}`)}
            </CardDescription>
          ) : (
            <CardDescription>{t("assessment.blueprint.not_yet")}</CardDescription>
          )}
        </CardHeader>
        {data.blueprint && (
          <CardContent className="space-y-3">
            {data.capability_matrix.map((entry) => (
              <CapabilityRow key={entry.key} entry={entry} />
            ))}
          </CardContent>
        )}
      </Card>

      {/* Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>{t("assessment.section.configuration")}</CardTitle>
          {!data.configuration_plan && <CardDescription>{t("assessment.configuration.not_yet")}</CardDescription>}
        </CardHeader>
        {data.configuration_plan && (
          <CardContent className="space-y-2">
            <p className="text-sm">
              {t("company_setup.plan.status")}: <Badge>{data.configuration_plan.status}</Badge>
            </p>
            <ul className="space-y-1 text-sm text-muted-foreground">
              {data.configuration_plan.items.map((item) => (
                <li key={item.id} className="flex items-center gap-2">
                  <Badge variant={item.status === "applied" ? "secondary" : "outline"}>{item.status}</Badge>
                  {item.decision_key}
                </li>
              ))}
            </ul>
          </CardContent>
        )}
      </Card>

      {/* Capability Gaps */}
      <Card>
        <CardHeader>
          <CardTitle>{t("assessment.section.capability_gaps")}</CardTitle>
          <CardDescription>{t("assessment.capability_gaps.description")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {gapItems.length === 0 && data.blueprint && (
            <p className="text-sm text-muted-foreground">{t("assessment.capability_gaps.none")}</p>
          )}
          {gapItems.map((entry) => (
            <CapabilityRow key={entry.key} entry={entry} />
          ))}
          <Separator />
          <p className="text-xs font-medium text-muted-foreground">{t("assessment.future_needs.title")}</p>
          <ul className="space-y-2">
            {data.future_needs.map((need) => (
              <FutureNeedRow key={need.key} need={need} />
            ))}
          </ul>
        </CardContent>
      </Card>

      {/* Implementation Scope */}
      <Card>
        <CardHeader>
          <CardTitle>{t("assessment.section.implementation_scope")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div>
            <p className="text-sm font-medium">{t("assessment.implementation_scope.in_scope")}</p>
            <ul className="mt-1 list-inside list-disc text-sm text-muted-foreground">
              {actionableItems.length === 0 && <li>{t("assessment.implementation_scope.none_yet")}</li>}
              {actionableItems.map((e) => (
                <li key={e.key}>{e.key}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-sm font-medium">{t("assessment.implementation_scope.needs_extension")}</p>
            <ul className="mt-1 list-inside list-disc text-sm text-muted-foreground">
              {gapItems.length === 0 && <li>{t("assessment.implementation_scope.none_yet")}</li>}
              {gapItems.map((e) => (
                <li key={e.key}>
                  {e.key} ({e.category})
                </li>
              ))}
            </ul>
          </div>
        </CardContent>
      </Card>

      {/* Commercial Inputs */}
      <Card>
        <CardHeader>
          <CardTitle>{t("assessment.section.commercial_inputs")}</CardTitle>
          <CardDescription>{t("assessment.commercial_inputs.description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <ProfileField
              label={t("company_setup.profile.employee_count")}
              value={data.commercial_inputs.employee_count}
            />
            <ProfileField
              label={t("company_setup.profile.desired_user_count")}
              value={data.commercial_inputs.desired_user_count}
            />
            <ProfileField label={t("company_setup.profile.branch_count")} value={data.commercial_inputs.branch_count} />
            <ProfileField
              label={t("company_setup.profile.warehouse_count")}
              value={data.commercial_inputs.warehouse_count}
            />
            <ProfileField
              label={t("assessment.commercial.recommended_edition")}
              value={data.commercial_inputs.recommended_edition_label}
            />
            <ProfileField
              label={t("assessment.commercial.actionable_count")}
              value={data.commercial_inputs.actionable_capability_count}
            />
            <ProfileField
              label={t("assessment.commercial.gap_count")}
              value={data.commercial_inputs.gap_capability_count}
            />
            <ProfileField
              label={t("assessment.commercial.custom_dev_count")}
              value={data.commercial_inputs.custom_development_needed_count}
            />
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}

function ProfileField({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value ?? "—"}</dd>
    </div>
  );
}

function CapabilityRow({ entry }: { entry: CapabilityMatrixEntry }) {
  const { t } = useI18n();
  return (
    <div className="rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{entry.key}</span>
        <Badge variant={CATEGORY_BADGE_VARIANT[entry.category] ?? "outline"}>{entry.category}</Badge>
        {entry.actionable ? (
          <Badge variant="secondary">{t("company_setup.blueprint.actionable")}</Badge>
        ) : (
          <Badge variant="outline">{t("company_setup.blueprint.capability_gap")}</Badge>
        )}
        {entry.applied_status && <Badge variant={entry.applied_status === "applied" ? "secondary" : "outline"}>{entry.applied_status}</Badge>}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{entry.reason}</p>
    </div>
  );
}

function FutureNeedRow({ need }: { need: FutureNeed }) {
  const { t } = useI18n();
  return (
    <li className="rounded-md border border-dashed p-3 text-sm">
      <p className="font-medium">{t(FUTURE_NEED_LABEL_KEYS[need.key] ?? need.key)}</p>
      <p className="mt-1 text-xs text-muted-foreground">{need.note}</p>
    </li>
  );
}
