"""Repository implementations for the Identity module (Phase 8 §7 — Repository pattern)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.infrastructure.master_data_models import Partner, Product
from src.modules.identity.infrastructure.models import (
    AppUser,
    AuditLog,
    Branch,
    Company,
    Currency,
    Permission,
    Role,
    RolePermission,
    UserCompanyAccess,
    UserRole,
)


class CompanyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, company: Company) -> Company:
        self.session.add(company)
        await self.session.flush()
        return company

    async def get_by_id(self, company_id: UUID) -> Company | None:
        result = await self.session.execute(
            select(Company).where(Company.id == company_id, Company.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_vat_number(self, vat_number: str) -> Company | None:
        result = await self.session.execute(
            select(Company).where(Company.vat_number == vat_number, Company.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()


class BranchRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, branch: Branch) -> Branch:
        self.session.add(branch)
        await self.session.flush()
        return branch

    async def list_by_company(self, company_id: UUID) -> list[Branch]:
        result = await self.session.execute(
            select(Branch).where(Branch.company_id == company_id, Branch.deleted_at.is_(None))
        )
        return list(result.scalars().all())


class CurrencyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_code(self, code: str) -> Currency | None:
        result = await self.session.execute(select(Currency).where(Currency.code == code))
        return result.scalar_one_or_none()


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, user: AppUser) -> AppUser:
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: UUID) -> AppUser | None:
        result = await self.session.execute(
            select(AppUser).where(AppUser.id == user_id, AppUser.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> AppUser | None:
        result = await self.session.execute(
            select(AppUser).where(AppUser.email == email.lower(), AppUser.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def grant_company_access(
        self, user_id: UUID, company_id: UUID, branch_id: UUID | None = None
    ) -> UserCompanyAccess:
        access = UserCompanyAccess(user_id=user_id, company_id=company_id, branch_id=branch_id)
        self.session.add(access)
        await self.session.flush()
        return access

    async def list_authorized_companies(self, user_id: UUID) -> list[UserCompanyAccess]:
        result = await self.session.execute(
            select(UserCompanyAccess).where(UserCompanyAccess.user_id == user_id)
        )
        return list(result.scalars().all())


class RoleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, role: Role) -> Role:
        self.session.add(role)
        await self.session.flush()
        return role

    async def get_permission_by_code(self, code: str) -> Permission | None:
        result = await self.session.execute(select(Permission).where(Permission.code == code))
        return result.scalar_one_or_none()

    async def grant_permission(self, role_id: UUID, permission_id: UUID) -> None:
        self.session.add(RolePermission(role_id=role_id, permission_id=permission_id))
        await self.session.flush()

    async def assign_to_user(self, user_id: UUID, role_id: UUID) -> None:
        self.session.add(UserRole(user_id=user_id, role_id=role_id))
        await self.session.flush()

    async def get_user_permission_codes(self, user_id: UUID, company_id: UUID) -> set[str]:
        """All permission codes granted to `user_id` via roles scoped to `company_id`."""
        result = await self.session.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, Role.company_id == company_id)
        )
        return set(result.scalars().all())


class AuditLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(
        self,
        *,
        tenant_id: UUID,
        company_id: UUID,
        user_id: UUID | None,
        target_table: str,
        target_id: UUID,
        field_name: str,
        old_value: str | None,
        new_value: str | None,
    ) -> None:
        self.session.add(
            AuditLog(
                tenant_id=tenant_id,
                company_id=company_id,
                user_id=user_id,
                target_table=target_table,
                target_id=target_id,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
            )
        )
        await self.session.flush()

    async def list_by_company(
        self,
        company_id: UUID,
        *,
        target_table: str | None = None,
        user_id: UUID | None = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """FR-RPT-004 — filterable, exportable audit log report."""
        stmt = select(AuditLog).where(AuditLog.company_id == company_id)
        if target_table is not None:
            stmt = stmt.where(AuditLog.target_table == target_table)
        if user_id is not None:
            stmt = stmt.where(AuditLog.user_id == user_id)
        stmt = stmt.order_by(AuditLog.changed_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class PartnerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, partner: Partner) -> Partner:
        self.session.add(partner)
        await self.session.flush()
        return partner

    async def get_by_id(self, partner_id: UUID) -> Partner | None:
        result = await self.session.execute(
            select(Partner).where(Partner.id == partner_id, Partner.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_by_company(self, company_id: UUID, *, customers_only: bool = False, vendors_only: bool = False) -> list[Partner]:
        stmt = select(Partner).where(Partner.company_id == company_id, Partner.deleted_at.is_(None))
        if customers_only:
            stmt = stmt.where(Partner.is_customer.is_(True))
        if vendors_only:
            stmt = stmt.where(Partner.is_vendor.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ProductRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, product: Product) -> Product:
        self.session.add(product)
        await self.session.flush()
        return product

    async def get_by_id(self, product_id: UUID) -> Product | None:
        result = await self.session.execute(
            select(Product).where(Product.id == product_id, Product.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_sku(self, company_id: UUID, sku: str) -> Product | None:
        result = await self.session.execute(
            select(Product).where(
                Product.company_id == company_id, Product.sku == sku, Product.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def list_by_company(self, company_id: UUID) -> list[Product]:
        result = await self.session.execute(
            select(Product).where(Product.company_id == company_id, Product.deleted_at.is_(None))
        )
        return list(result.scalars().all())
