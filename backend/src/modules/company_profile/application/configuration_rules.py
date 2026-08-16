"""Configuration Plan item generation (Adaptive ERP Stage 2.4 v1).

Pure function, no DB/HTTP -- mirrors blueprint_rules.py's own pattern.
Reads an approved Blueprint's `decisions` (as stored, list of plain dicts)
and shapes the subset this stage actually knows how to apply into
ConfigurationPlanItem specs. Only keys in SUPPORTED_DECISION_KEYS ever
produce an item; everything else (including a decision the Blueprint
itself marked actionable=True) is silently skipped here rather than
guessed at -- widening what Stage 2.4 applies is a deliberate, reviewed
change to SUPPORTED_DECISION_KEYS, never an accident of this function.
"""

from typing import Any

from src.modules.company_profile.domain.entities import SUPPORTED_DECISION_KEYS


def _build_item(key: str, decision: dict[str, Any]) -> dict[str, Any]:
    if key == "po_approval_threshold":
        return {
            "decision_key": key,
            "target_type": "company",
            "action": "set_field",
            "payload": {"field": "po_approval_threshold", "value": decision["decision"]},
        }
    if key == "provision_role_templates":
        return {
            "decision_key": key,
            "target_type": "role",
            "action": "create_roles",
            "payload": {"names": list(decision["decision"])},
        }
    raise ValueError(f"no ConfigurationPlanItem builder registered for supported key {key!r}")


def build_plan_items(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """decisions: ErpBlueprint.decisions as persisted (list of
    {key, category, decision, reason, actionable}). Returns [] when none of
    the Blueprint's decisions are both actionable and in
    SUPPORTED_DECISION_KEYS -- an empty Plan is valid, not an error."""
    by_key = {d["key"]: d for d in decisions}
    items = []
    for key in SUPPORTED_DECISION_KEYS:
        decision = by_key.get(key)
        if decision is None or not decision["actionable"]:
            continue
        items.append(_build_item(key, decision))
    return items
