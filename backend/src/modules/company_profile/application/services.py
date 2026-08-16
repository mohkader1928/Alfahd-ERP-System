"""Application service for Company Profile (Adaptive ERP Stage 2.1).

Read/create/update only — no sizing, blueprint, or configuration logic
lives here (those are Stage 2.2-2.4, separate services in this same
module per docs/adaptive/06-configuration-engine-architecture.md §6.2).
"""

import uuid
from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.company_profile.application.blueprint_rules import generate_decisions
from src.modules.company_profile.application.configuration_rules import build_plan_items
from src.modules.company_profile.application.sizing_rules import score_profile
from src.modules.company_profile.domain.entities import CompanyProfile as CompanyProfileDomain
from src.modules.company_profile.infrastructure.models import (
    CompanyProfile,
    ConfigurationPlan,
    ConfigurationPlanItem,
    ErpBlueprint,
    SizingResult,
)
from src.modules.company_profile.infrastructure.repositories import (
    CompanyProfileRepository,
    ConfigurationPlanItemRepository,
    ConfigurationPlanRepository,
    ErpBlueprintRepository,
    SizingResultRepository,
    SizingRuleSetRepository,
)
from src.modules.identity.application.services import CompanyService, UserManagementService
from src.modules.identity.infrastructure.models import Role
from src.modules.identity.infrastructure.repositories import AuditLogRepository


class ConfigurationApplyError(Exception):
    """Raised by ConfigurationEngineService._apply_item() to abort the
    current Apply attempt cleanly -- caught by apply() to trigger the
    nested-transaction rollback and mark the Plan/item as failed."""

# Fields a caller may set — everything on the domain entity except its
# identity columns (id/tenant_id/company_id), which are never client-supplied
# (docs/adaptive/12 Principle 3 — same "company_id is never client-supplied"
# rule already proven by test_insert_isolation_company_id_is_never_client_supplied
# in the Golden Core's own multi-tenancy isolation test suite).
_WRITABLE_FIELDS = tuple(
    f.name for f in fields(CompanyProfileDomain) if f.name not in ("id", "tenant_id", "company_id")
)


class CompanyProfileService:
    def __init__(self, profile_repo: CompanyProfileRepository, audit_repo: AuditLogRepository):
        self.profile_repo = profile_repo
        self.audit_repo = audit_repo

    async def get(self, *, company_id: UUID) -> CompanyProfile | None:
        return await self.profile_repo.get_by_company(company_id)

    async def create(
        self, *, tenant_id: UUID, company_id: UUID, user_id: UUID | None, values: dict[str, Any]
    ) -> CompanyProfile:
        existing = await self.profile_repo.get_by_company(company_id)
        if existing is not None:
            raise ValueError("A company_profile already exists for this company — use update instead")

        # Validate via the domain entity first (raises ValueError on bad
        # input, e.g. a negative count or an unknown approval_rigor_preference)
        # before ever touching the ORM/DB — same "validate in domain, persist
        # in infrastructure" separation the Golden Core's Company entity uses.
        domain_values = {k: v for k, v in values.items() if k in _WRITABLE_FIELDS}
        CompanyProfileDomain(id=uuid.uuid4(), tenant_id=tenant_id, company_id=company_id, **domain_values)

        profile = CompanyProfile(
            tenant_id=tenant_id,
            company_id=company_id,
            created_by=user_id,
            **domain_values,
        )
        profile = await self.profile_repo.add(profile)

        for field_name, new_value in domain_values.items():
            await self.audit_repo.record(
                tenant_id=tenant_id,
                company_id=company_id,
                user_id=user_id,
                target_table="company_profile",
                target_id=profile.id,
                field_name=field_name,
                old_value=None,
                new_value=str(new_value) if new_value is not None else None,
            )
        return profile

    async def update(
        self, *, company_id: UUID, tenant_id: UUID, user_id: UUID | None, values: dict[str, Any]
    ) -> CompanyProfile:
        profile = await self.profile_repo.get_by_company(company_id)
        if profile is None:
            raise LookupError("No company_profile exists for this company yet — create one first")

        domain_values = {k: v for k, v in values.items() if k in _WRITABLE_FIELDS}
        # Merge onto current values so a partial update still validates a
        # complete, consistent entity (e.g. changing only coa_depth_preference
        # still re-checks approval_rigor_preference's current value).
        current = {name: getattr(profile, name) for name in _WRITABLE_FIELDS}
        merged = {**current, **domain_values}
        CompanyProfileDomain(id=profile.id, tenant_id=tenant_id, company_id=company_id, **merged)

        old_values = dict(current)
        for field_name, new_value in domain_values.items():
            setattr(profile, field_name, new_value)
        profile.updated_by = user_id

        for field_name, new_value in domain_values.items():
            old_value = old_values[field_name]
            if old_value != new_value:
                await self.audit_repo.record(
                    tenant_id=tenant_id,
                    company_id=company_id,
                    user_id=user_id,
                    target_table="company_profile",
                    target_id=profile.id,
                    field_name=field_name,
                    old_value=str(old_value) if old_value is not None else None,
                    new_value=str(new_value) if new_value is not None else None,
                )
        return profile


# Fields score_profile() actually reads from a CompanyProfile — kept
# explicit (rather than dumping every ORM column) so an unrelated future
# column addition to company_profile never silently changes sizing input
# without a deliberate update here.
_SIZING_INPUT_FIELDS = (
    "employee_count",
    "branch_count",
    "cost_center_tracking_needed",
    "is_service_business",
    "warehouse_count",
    "monthly_sales_order_volume",
    "monthly_purchase_order_volume",
    "sku_count_estimate",
    "coa_depth_preference",
    "multi_currency_requested",
    "withholding_tax_needed",
    "owns_fixed_assets",
    "fixed_asset_count_estimate",
    "approval_rigor_preference",
    "desired_user_count",
    "two_factor_required",
)


class SizingEngineService:
    """docs/adaptive/04-erp-sizing-engine-spec.md. Deterministic: the same
    (profile, active rule_version) always produces the same SizingResult
    -- score_profile() is a pure function (application/sizing_rules.py),
    this service only handles fetching the inputs and persisting the
    output."""

    def __init__(
        self,
        profile_repo: CompanyProfileRepository,
        rule_set_repo: SizingRuleSetRepository,
        result_repo: SizingResultRepository,
    ):
        self.profile_repo = profile_repo
        self.rule_set_repo = rule_set_repo
        self.result_repo = result_repo

    async def compute(self, *, tenant_id: UUID, company_id: UUID) -> SizingResult:
        profile = await self.profile_repo.get_by_company(company_id)
        if profile is None:
            raise LookupError("No company_profile exists for this company yet — create one first")

        rule_set = await self.rule_set_repo.get_active()
        if rule_set is None:
            raise LookupError("No active sizing_rule_set exists — this is a deployment/seed problem, not a user error")

        profile_values = {name: getattr(profile, name) for name in _SIZING_INPUT_FIELDS}
        dimension_scores = score_profile(profile_values, rule_set.rules)

        result = SizingResult(
            tenant_id=tenant_id,
            company_id=company_id,
            company_profile_id=profile.id,
            rule_version=rule_set.version,
            dimension_scores={dim: {"score": ds.score, "reason": ds.reason} for dim, ds in dimension_scores.items()},
        )
        return await self.result_repo.add(result)

    async def get_latest(self, *, company_id: UUID) -> SizingResult | None:
        return await self.result_repo.get_latest_for_company(company_id)


class BlueprintService:
    """docs/adaptive/05-erp-blueprint-spec.md. Generates a draft Blueprint
    from the company's latest SizingResult; a separate, explicit approve()
    call is the only way a Blueprint becomes 'approved' -- generation is
    never itself an approval (docs/adaptive/12 Principle 5, and the
    governing spec's "AI/engine must not directly mutate production
    configuration without explicit approval" rule applies here even though
    no AI is involved yet)."""

    def __init__(
        self,
        profile_repo: CompanyProfileRepository,
        rule_set_repo: SizingRuleSetRepository,
        result_repo: SizingResultRepository,
        blueprint_repo: ErpBlueprintRepository,
    ):
        self.profile_repo = profile_repo
        self.rule_set_repo = rule_set_repo
        self.result_repo = result_repo
        self.blueprint_repo = blueprint_repo

    async def generate(self, *, tenant_id: UUID, company_id: UUID, user_id: UUID | None) -> ErpBlueprint:
        profile = await self.profile_repo.get_by_company(company_id)
        if profile is None:
            raise LookupError("No company_profile exists for this company yet — create one first")

        sizing_result = await self.result_repo.get_latest_for_company(company_id)
        if sizing_result is None:
            raise LookupError("No sizing result exists for this company yet — run sizing first")

        rule_set = await self.rule_set_repo.get_by_version(sizing_result.rule_version)
        if rule_set is None:
            raise LookupError(f"Rule set {sizing_result.rule_version!r} referenced by the sizing result no longer exists")

        profile_values = {name: getattr(profile, name) for name in _SIZING_INPUT_FIELDS}
        thresholds = rule_set.rules.get("blueprint_decisions", {})
        decisions, enabled_modules = generate_decisions(profile_values, sizing_result.dimension_scores, thresholds)

        next_version = await self.blueprint_repo.get_next_version(company_id)
        blueprint = ErpBlueprint(
            tenant_id=tenant_id,
            company_id=company_id,
            company_profile_id=profile.id,
            sizing_result_id=sizing_result.id,
            blueprint_version=next_version,
            status="draft",
            decisions=[
                {
                    "key": d.key,
                    "category": d.category,
                    "decision": d.decision,
                    "reason": d.reason,
                    "actionable": d.actionable,
                }
                for d in decisions
            ],
            enabled_modules=enabled_modules,
            created_by=user_id,
        )
        return await self.blueprint_repo.add(blueprint)

    async def approve(self, *, company_id: UUID, blueprint_id: UUID, user_id: UUID | None) -> ErpBlueprint:
        blueprint = await self.blueprint_repo.get_by_id(blueprint_id)
        if blueprint is None or blueprint.company_id != company_id:
            raise LookupError("Blueprint not found")
        if blueprint.status != "draft":
            raise ValueError(f"Only a draft Blueprint can be approved (current status: {blueprint.status!r})")

        # Supersede whatever was previously the approved Blueprint, if any
        # -- exactly one "currently approved" Blueprint per company at a
        # time, never deleted, always superseded forward (docs/adaptive/05 §5.3).
        for existing in await self.blueprint_repo.list_for_company(company_id):
            if existing.status == "approved":
                existing.status = "superseded"
                existing.superseded_by_id = blueprint.id

        blueprint.status = "approved"
        blueprint.approved_at = datetime.now(UTC).replace(tzinfo=None)
        blueprint.approved_by = user_id
        return blueprint

    async def get(self, *, blueprint_id: UUID) -> ErpBlueprint | None:
        return await self.blueprint_repo.get_by_id(blueprint_id)

    async def list_for_company(self, *, company_id: UUID) -> list[ErpBlueprint]:
        return await self.blueprint_repo.list_for_company(company_id)

    async def get_latest(self, *, company_id: UUID) -> ErpBlueprint | None:
        return await self.blueprint_repo.get_latest_for_company(company_id)


# The 4 canonical role-template names UserManagementService.seed_default_role_templates()
# (backend/src/modules/identity/application/services.py) creates as one atomic batch.
# ConfigurationEngineService needs to know these NAMES (not their permission
# codes) to decide, per company, whether that batch has already run --
# seed_default_role_templates() has no per-name existence check of its own,
# so calling it again on a company that already has some/all of them would
# create duplicates (Stage 2.4 Design & Safety Review §2.2).
CANONICAL_ROLE_TEMPLATE_NAMES = ("Accountant", "Sales", "Purchasing & Warehouse", "Read-Only Viewer")


class ConfigurationEngineService:
    """docs/adaptive/06-configuration-engine-architecture.md §6.1, narrowed
    to the Stage 2.4 v1 scope approved in the Design & Safety Review:
    Approved Blueprint -> Configuration Plan -> Validation -> Apply ->
    Verification -> Audit. Only two decision keys are ever turned into
    plan items (see application/configuration_rules.SUPPORTED_DECISION_KEYS)
    -- po_approval_threshold (Company.po_approval_threshold, via the one
    approved identity exception CompanyService.set_po_approval_threshold)
    and provision_role_templates (via the existing, unmodified
    UserManagementService.seed_default_role_templates() / create_role()).

    Every write happens through the SAME AsyncSession/AuthContext as the
    triggering request -- no second DB connection, no elevated context, no
    company_id ever taken from anywhere but the approved Blueprint itself.
    """

    def __init__(
        self,
        session: AsyncSession,
        blueprint_repo: ErpBlueprintRepository,
        plan_repo: ConfigurationPlanRepository,
        item_repo: ConfigurationPlanItemRepository,
        company_service: CompanyService,
        user_management_service: UserManagementService,
        audit_repo: AuditLogRepository,
    ):
        self.session = session
        self.blueprint_repo = blueprint_repo
        self.plan_repo = plan_repo
        self.item_repo = item_repo
        self.company_service = company_service
        self.user_management_service = user_management_service
        self.audit_repo = audit_repo

    async def create_plan(self, *, tenant_id: UUID, company_id: UUID, user_id: UUID | None) -> ConfigurationPlan:
        blueprint = await self.blueprint_repo.get_approved_for_company(company_id)
        if blueprint is None:
            raise LookupError("No approved Blueprint exists for this company -- approve one first")

        existing = await self.plan_repo.get_by_company_and_blueprint(company_id, blueprint.id)
        if existing is not None:
            raise ValueError(
                f"A Configuration Plan already exists for this Blueprint version (plan_id={existing.id})"
            )

        plan = ConfigurationPlan(
            tenant_id=tenant_id, company_id=company_id, blueprint_id=blueprint.id, status="draft", created_by=user_id
        )
        plan = await self.plan_repo.add(plan)

        for spec in build_plan_items(blueprint.decisions):
            await self.item_repo.add(
                ConfigurationPlanItem(
                    tenant_id=tenant_id,
                    company_id=company_id,
                    plan_id=plan.id,
                    decision_key=spec["decision_key"],
                    target_type=spec["target_type"],
                    action=spec["action"],
                    payload=spec["payload"],
                    status="pending",
                    created_by=user_id,
                )
            )
        return plan

    async def validate(self, *, plan_id: UUID, company_id: UUID) -> ConfigurationPlan:
        plan = await self.plan_repo.get_by_id(plan_id)
        if plan is None or plan.company_id != company_id:
            raise LookupError("Configuration Plan not found")
        if plan.status != "draft":
            raise ValueError(f"Only a draft Plan can be validated (current status: {plan.status!r})")

        blueprint = await self.blueprint_repo.get_by_id(plan.blueprint_id)
        if blueprint is None or blueprint.status != "approved":
            plan.status = "failed"
            plan.failure_reason = "Blueprint is no longer approved"
            return plan

        plan.status = "validated"
        plan.validated_at = datetime.now(UTC).replace(tzinfo=None)
        return plan

    async def apply(
        self, *, plan_id: UUID, tenant_id: UUID, company_id: UUID, user_id: UUID | None
    ) -> ConfigurationPlan:
        plan = await self.plan_repo.get_by_id(plan_id)
        if plan is None or plan.company_id != company_id:
            raise LookupError("Configuration Plan not found")
        if plan.status not in ("validated", "applied", "failed"):
            raise ValueError(f"Plan must be validated before it can be applied (current status: {plan.status!r})")

        # Re-checked fresh every time, including idempotent re-runs -- if a
        # newer Blueprint has since been approved (superseding this one),
        # Apply refuses rather than applying a stale decision set
        # (Stage 2.4 Design & Safety Review §3.3 point 6).
        blueprint = await self.blueprint_repo.get_by_id(plan.blueprint_id)
        if blueprint is None or blueprint.status != "approved":
            plan.status = "failed"
            plan.failure_reason = "Blueprint is no longer approved (superseded or missing) -- Apply refused"
            return plan

        items = await self.item_repo.list_for_plan(plan.id)
        failed_item: ConfigurationPlanItem | None = None
        try:
            async with self.session.begin_nested():
                for item in items:
                    failed_item = item
                    await self._apply_item(item, tenant_id=tenant_id, company_id=company_id, user_id=user_id)
                failed_item = None
        except Exception as exc:
            # Nested rollback above already reverted every write attempted
            # inside this Apply call (Company field + any Role rows) -- the
            # mutations below happen OUTSIDE the rolled-back savepoint, so
            # only the failure record itself survives to the outer commit.
            plan.status = "failed"
            plan.failure_reason = str(exc)
            if failed_item is not None:
                failed_item.status = "failed"
                failed_item.error_message = str(exc)
            return plan

        plan.status = "applied"
        plan.applied_at = datetime.now(UTC).replace(tzinfo=None)
        plan.failure_reason = None
        return plan

    async def _apply_item(
        self, item: ConfigurationPlanItem, *, tenant_id: UUID, company_id: UUID, user_id: UUID | None
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)

        if item.decision_key == "po_approval_threshold":
            raw_value = item.payload["value"]
            target = Decimal(str(raw_value)) if raw_value is not None else None
            company, changed = await self.company_service.set_po_approval_threshold(
                tenant_id=tenant_id, company_id=company_id, value=target, user_id=user_id
            )
            item.result = {
                "field": "po_approval_threshold",
                "new_value": str(target) if target is not None else None,
                "current_value": str(company.po_approval_threshold)
                if company.po_approval_threshold is not None
                else None,
            }
            item.status = "applied" if changed else "skipped_already_applied"
            item.applied_at = now
            return

        if item.decision_key == "provision_role_templates":
            existing_result = await self.session.execute(
                select(Role.name).where(
                    Role.company_id == company_id, Role.name.in_(CANONICAL_ROLE_TEMPLATE_NAMES)
                )
            )
            existing_names = set(existing_result.scalars().all())
            target_names = set(item.payload["names"])

            if target_names <= existing_names:
                item.status = "skipped_already_applied"
                item.result = {"already_existing": sorted(existing_names)}
                item.applied_at = now
                return

            if existing_names:
                # Partial state: seed_default_role_templates() is all-or-
                # nothing and create_role() alone doesn't know per-template
                # permission sets without duplicating identity's
                # definitions -- reported as a gap, never guessed at or
                # silently partially applied (Stage 2.4 Design & Safety
                # Review's "no workaround for a capability gap" rule).
                raise ConfigurationApplyError(
                    f"Partial role-template state for this company (existing: {sorted(existing_names)}, "
                    f"target: {sorted(target_names)}) -- Configuration Engine v1 only auto-provisions when "
                    "none of the canonical templates exist yet; reconcile manually via Settings > Roles."
                )

            created_roles = await self.user_management_service.seed_default_role_templates(company_id=company_id)
            for role in created_roles:
                await self.audit_repo.record(
                    tenant_id=tenant_id,
                    company_id=company_id,
                    user_id=user_id,
                    target_table="role",
                    target_id=role.id,
                    field_name="name",
                    old_value=None,
                    new_value=role.name,
                )
            item.result = {"created": [{"role_id": str(r.id), "role_name": r.name} for r in created_roles]}
            item.status = "applied"
            item.applied_at = now
            return

        raise ConfigurationApplyError(f"No apply handler registered for decision_key {item.decision_key!r}")

    async def get(self, *, plan_id: UUID) -> ConfigurationPlan | None:
        return await self.plan_repo.get_by_id(plan_id)

    async def list_items(self, *, plan_id: UUID) -> list[ConfigurationPlanItem]:
        return await self.item_repo.list_for_plan(plan_id)

    async def list_for_company(self, *, company_id: UUID) -> list[ConfigurationPlan]:
        return await self.plan_repo.list_for_company(company_id)
