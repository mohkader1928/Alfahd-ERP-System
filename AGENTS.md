# Alfahd ERP — Agent & Developer Entry Point

This repository must remain maintainable by human engineers and AI coding agents
(Claude, Codex, or equivalent). Do not rely on private chat history as project knowledge.

## Mandatory Reading Order

Before changing code or Production:

1. `docs/CURRENT_STATE.md` — current verified project and Production state.
2. `docs/08-system-architecture.md` — system architecture.
3. `docs/20-developer-guide.md` — development guidance.
4. `docs/11-testing.md` — testing requirements.
5. `docs/14-deployment.md` — deployment documentation.
6. `docs/21-disaster-recovery-and-rollback.md` — recovery safety rules.
7. `docs/RELEASE-RUNBOOK.md` — current Production release and rollback procedure.

When working under a directory containing its own `AGENTS.md`, read and follow
that file as well. In particular, `frontend/AGENTS.md` contains Next.js-specific rules.

## Source of Truth

Repository documentation and verified runtime evidence are the source of truth.

If documentation conflicts with the running Production environment:
- do not guess;
- verify the runtime safely;
- record the discrepancy;
- update the documentation through the normal review process.

Do not treat Claude, Codex, ChatGPT, terminal history, or any individual developer's
memory as the sole source of operational knowledge.

## Change Discipline

Use this sequence for material changes:

Audit -> Proposal -> Owner Approval -> Implementation -> Tests -> Staging/Controlled
Validation -> Owner Acceptance -> Release -> Monitoring.

Do not commit, push, tag, deploy, migrate, restart Production services, or perform
destructive operations without the required approval.

## Production Safety

Never perform blind destructive recovery commands such as:
- `git reset --hard`
- `git clean`
- `docker compose down -v`
- unreviewed `alembic downgrade`
- manual modification of `alembic_version`
- destructive database restore without explicit approval

Never store passwords, tokens, private keys, database credentials, or other secrets
in repository documentation.

Before every Production release or schema migration, create and verify the required
backup according to the release/recovery runbooks.

## Database Migrations

Do not assume a migration is safely reversible.

Before applying a Production migration:
- identify the current DB revision;
- identify the target code revision;
- review the migration;
- create a verified backup;
- define the rollback/data-preservation strategy.

## Testing

Run the tests appropriate to the changed area before release.
Security, tenant isolation, accounting integrity, inventory integrity, and data
integrity regressions are release blockers.

## Current Operational Principle

The system must be transferable between AI agents and professional engineers with
minimal undocumented context.

Any operational knowledge required to safely develop, deploy, recover, or maintain
the system must be captured in the repository documentation rather than existing
only in chat history.
