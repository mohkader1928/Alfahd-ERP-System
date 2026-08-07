"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SettingsShell } from "@/components/erp/settings-shell/settings-shell";
import { FormView } from "@/components/erp/form-view/form-view";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/erp/states/error-state";
import { NotFoundState } from "@/components/erp/states/not-found";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { ApiError } from "@/lib/api-client";
import { toastError, toastSuccess } from "@/lib/toast";
import type { Role, UserDetail } from "@/features/identity/api/types";

export default function UserDetailPage({ params }: { params: Promise<{ userId: string }> }) {
  const { userId } = use(params);
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const userQuery = useQuery({
    queryKey: ["user", companyId, userId],
    queryFn: () => identityApi.getUser(companyId, userId),
  });
  const rolesQuery = useQuery({
    queryKey: ["roles", companyId],
    queryFn: () => identityApi.listRoles(companyId),
  });

  if (userQuery.isError && userQuery.error instanceof ApiError && userQuery.error.status === 404) {
    return (
      <SettingsShell>
        <NotFoundState label={t("settings.users.user_not_found")} />
      </SettingsShell>
    );
  }
  if (userQuery.isError) {
    return (
      <SettingsShell>
        <ErrorState onRetry={() => userQuery.refetch()} />
      </SettingsShell>
    );
  }
  if (userQuery.isLoading || !userQuery.data || rolesQuery.isLoading || !rolesQuery.data) {
    return (
      <SettingsShell>
        <Skeleton className="h-96 w-full" />
      </SettingsShell>
    );
  }

  return (
    <SettingsShell>
      <UserRolesForm
        key={userQuery.data.id}
        user={userQuery.data}
        allRoles={rolesQuery.data}
        companyId={companyId}
        userId={userId}
      />
    </SettingsShell>
  );
}

function UserRolesForm({
  user,
  allRoles,
  companyId,
  userId,
}: {
  user: UserDetail;
  allRoles: Role[];
  companyId: string;
  userId: string;
}) {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const assignedRoleIds = new Set(user.roles.map((r) => r.id));

  const toggleMutation = useMutation({
    mutationFn: ({ roleId, assign }: { roleId: string; assign: boolean }) =>
      assign
        ? identityApi.assignRole(companyId, userId, roleId)
        : identityApi.removeRole(companyId, userId, roleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user", companyId, userId] });
      queryClient.invalidateQueries({ queryKey: ["users", companyId] });
      queryClient.invalidateQueries({ queryKey: ["me-permissions"] });
      toastSuccess(t("toast.success_title"), t("settings.users.roles_updated"));
    },
    onError: (err) => {
      const message = err instanceof ApiError ? err.detail : t("common.error");
      toastError(t("toast.error_title"), message);
    },
  });

  return (
    <FormView
      title={user.full_name}
      statusBadge={<Badge variant={user.is_active ? "secondary" : "outline"}>{user.is_active ? t("settings.users.active") : t("settings.users.inactive")}</Badge>}
      breadcrumbs={[{ label: t("settings.section.users"), href: "/settings/users" }, { label: user.full_name }]}
      onCancel={() => router.push("/settings/users")}
    >
      <div className="space-y-6">
        <p className="text-sm text-muted-foreground">{user.email}</p>

        <div className="space-y-2">
          <p className="text-sm font-semibold">{t("settings.users.roles")}</p>
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {allRoles.map((role) => (
              <label key={role.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={assignedRoleIds.has(role.id)}
                  disabled={toggleMutation.isPending}
                  onChange={(e) => toggleMutation.mutate({ roleId: role.id, assign: e.target.checked })}
                />
                {role.name}
                {role.is_system && (
                  <Badge variant="outline" className="text-xs">
                    {t("settings.security.system")}
                  </Badge>
                )}
              </label>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-sm font-semibold">{t("settings.users.company_access")}</p>
          <div className="space-y-1">
            {user.company_access.map((access) => (
              <div key={`${access.company_id}-${access.branch_id ?? "all"}`} className="text-sm">
                {access.company_name}
                {access.branch_name && (
                  <span className="text-muted-foreground"> — {access.branch_name}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </FormView>
  );
}
