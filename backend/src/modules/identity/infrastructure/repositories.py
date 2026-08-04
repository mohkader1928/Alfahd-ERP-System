"""Repository implementations for the Identity module (Phase 8 §7 — Repository pattern)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.infrastructure.master_data_models import (
    Partner,
    PartnerAddress,
    Product,
    ProductCategory,
    UnitOfMeasure,
)
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

    async def list_by_company(self, company_id: UUID) -> list[Role]:
        result = await self.session.execute(
            select(Role).where(Role.company_id == company_id).order_by(Role.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, company_id: UUID, role_id: UUID) -> Role | None:
        result = await self.session.execute(
            select(Role).where(Role.id == role_id, Role.company_id == company_id)
        )
        return result.scalar_one_or_none()

    async def list_all_permissions(self) -> list[Permission]:
        """Permission is a global catalog (Phase 7), not company-scoped —
        every company chooses from the same fixed set."""
        result = await self.session.execute(select(Permission).order_by(Permission.code))
        return list(result.scalars().all())

    async def get_role_permission_codes(self, role_id: UUID) -> set[str]:
        result = await self.session.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        return set(result.scalars().all())

    async def set_permissions(self, role_id: UUID, permission_ids: list[UUID]) -> None:
        """Replaces a role's entire permission set — matches the checkbox-
        matrix + Save UX (Settings Architecture Foundation milestone), the
        first API able to change permissions on an already-existing role;
        previously a role's permissions were fixed at creation time
        (bootstrap/company-create), a known, previously-documented gap."""
        await self.session.execute(
            RolePermission.__table__.delete().where(RolePermission.role_id == role_id)
        )
        for permission_id in permission_ids:
            self.session.add(RolePermission(role_id=role_id, permission_id=permission_id))
        await self.session.flush()


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

    async def get_by_id(self, partner_id: UUID, *, include_archived: bool = False) -> Partner | None:
        stmt = select(Partner).where(Partner.id == partner_id)
        if not include_archived:
            stmt = stmt.where(Partner.deleted_at.is_(None))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_company(
        self,
        company_id: UUID,
        *,
        customers_only: bool = False,
        vendors_only: bool = False,
        employees_only: bool = False,
        parent_partner_id: UUID | None = None,
        search: str | None = None,
        include_archived: bool = False,
    ) -> list[Partner]:
        stmt = select(Partner).where(Partner.company_id == company_id)
        if not include_archived:
            stmt = stmt.where(Partner.deleted_at.is_(None))
        if customers_only:
            stmt = stmt.where(Partner.is_customer.is_(True))
        if vendors_only:
            stmt = stmt.where(Partner.is_vendor.is_(True))
        if employees_only:
            stmt = stmt.where(Partner.is_employee.is_(True))
        if parent_partner_id is not None:
            stmt = stmt.where(Partner.parent_partner_id == parent_partner_id)
        if search:
            needle = f"%{search}%"
            stmt = stmt.where(
                Partner.name.ilike(needle)
                | Partner.name_ar.ilike(needle)
                | Partner.vat_number.ilike(needle)
                | Partner.cr_number.ilike(needle)
                | Partner.email.ilike(needle)
                | Partner.phone.ilike(needle)
                | Partner.mobile.ilike(needle)
            )
        result = await self.session.execute(stmt.order_by(Partner.name))
        return list(result.scalars().all())


class PartnerAddressRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, address: PartnerAddress) -> PartnerAddress:
        self.session.add(address)
        await self.session.flush()
        return address

    async def get_by_id(self, company_id: UUID, address_id: UUID) -> PartnerAddress | None:
        result = await self.session.execute(
            select(PartnerAddress).where(PartnerAddress.id == address_id, PartnerAddress.company_id == company_id)
        )
        return result.scalar_one_or_none()

    async def list_by_partner(self, company_id: UUID, partner_id: UUID) -> list[PartnerAddress]:
        result = await self.session.execute(
            select(PartnerAddress)
            .where(PartnerAddress.company_id == company_id, PartnerAddress.partner_id == partner_id)
            .order_by(PartnerAddress.type, PartnerAddress.created_at)
        )
        return list(result.scalars().all())

    async def unset_other_defaults(
        self, company_id: UUID, partner_id: UUID, type_: str, *, exclude_id: UUID | None = None
    ) -> None:
        """Enforces "at most one default per (partner, type)" at the
        application layer rather than a DB constraint — keeps the migration
        simple and matches how similar single-default invariants are
        handled elsewhere in this codebase (e.g. Branch.is_main has no DB
        constraint either)."""
        stmt = select(PartnerAddress).where(
            PartnerAddress.company_id == company_id,
            PartnerAddress.partner_id == partner_id,
            PartnerAddress.type == type_,
            PartnerAddress.is_default.is_(True),
        )
        if exclude_id is not None:
            stmt = stmt.where(PartnerAddress.id != exclude_id)
        result = await self.session.execute(stmt)
        for row in result.scalars().all():
            row.is_default = False
        await self.session.flush()

    async def delete(self, address: PartnerAddress) -> None:
        await self.session.delete(address)
        await self.session.flush()


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

    async def list_by_company(
        self, company_id: UUID, *, category_id: UUID | None = None, search: str | None = None
    ) -> list[Product]:
        stmt = select(Product).where(Product.company_id == company_id, Product.deleted_at.is_(None))
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
        if search:
            needle = f"%{search}%"
            stmt = stmt.where(
                Product.sku.ilike(needle) | Product.name.ilike(needle) | Product.name_ar.ilike(needle)
            )
        result = await self.session.execute(stmt.order_by(Product.name))
        return list(result.scalars().all())

    async def count_by_category(self, company_id: UUID, category_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Product)
            .where(Product.company_id == company_id, Product.category_id == category_id, Product.deleted_at.is_(None))
        )
        return result.scalar_one()

    async def count_by_uom(self, company_id: UUID, uom_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Product)
            .where(Product.company_id == company_id, Product.uom_id == uom_id, Product.deleted_at.is_(None))
        )
        return result.scalar_one()


class ProductCategoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, category: ProductCategory) -> ProductCategory:
        self.session.add(category)
        await self.session.flush()
        return category

    async def get_by_id(self, company_id: UUID, category_id: UUID) -> ProductCategory | None:
        result = await self.session.execute(
            select(ProductCategory).where(
                ProductCategory.id == category_id, ProductCategory.company_id == company_id
            )
        )
        return result.scalar_one_or_none()

    async def list_by_company(self, company_id: UUID) -> list[ProductCategory]:
        result = await self.session.execute(
            select(ProductCategory).where(ProductCategory.company_id == company_id).order_by(ProductCategory.name)
        )
        return list(result.scalars().all())

    async def find_sibling_by_name(
        self, company_id: UUID, parent_id: UUID | None, name: str, *, exclude_id: UUID | None = None
    ) -> ProductCategory | None:
        """Case-insensitive duplicate-name check among categories sharing the
        same parent (root categories share parent_id=NULL as their group)."""
        stmt = select(ProductCategory).where(
            ProductCategory.company_id == company_id,
            func.lower(ProductCategory.name) == name.lower(),
        )
        stmt = stmt.where(ProductCategory.parent_id == parent_id) if parent_id is not None else stmt.where(
            ProductCategory.parent_id.is_(None)
        )
        if exclude_id is not None:
            stmt = stmt.where(ProductCategory.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_children(self, company_id: UUID, category_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(ProductCategory)
            .where(ProductCategory.company_id == company_id, ProductCategory.parent_id == category_id)
        )
        return result.scalar_one()

    async def delete(self, category: ProductCategory) -> None:
        await self.session.delete(category)
        await self.session.flush()


class UnitOfMeasureRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, uom: UnitOfMeasure) -> UnitOfMeasure:
        self.session.add(uom)
        await self.session.flush()
        return uom

    async def get_by_id(self, company_id: UUID, uom_id: UUID) -> UnitOfMeasure | None:
        result = await self.session.execute(
            select(UnitOfMeasure).where(UnitOfMeasure.id == uom_id, UnitOfMeasure.company_id == company_id)
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, company_id: UUID, code: str) -> UnitOfMeasure | None:
        result = await self.session.execute(
            select(UnitOfMeasure).where(
                UnitOfMeasure.company_id == company_id, func.lower(UnitOfMeasure.code) == code.lower()
            )
        )
        return result.scalar_one_or_none()

    async def list_by_company(
        self, company_id: UUID, *, active: bool | None = None, search: str | None = None
    ) -> list[UnitOfMeasure]:
        stmt = select(UnitOfMeasure).where(UnitOfMeasure.company_id == company_id)
        if active is not None:
            stmt = stmt.where(UnitOfMeasure.active.is_(active))
        if search:
            needle = f"%{search}%"
            stmt = stmt.where(
                UnitOfMeasure.name.ilike(needle)
                | UnitOfMeasure.name_ar.ilike(needle)
                | UnitOfMeasure.code.ilike(needle)
            )
        result = await self.session.execute(stmt.order_by(UnitOfMeasure.name))
        return list(result.scalars().all())
