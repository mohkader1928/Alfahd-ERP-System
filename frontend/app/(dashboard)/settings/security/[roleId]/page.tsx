"use client";

import { use, useState } from "react";
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
import type { Permission } from "@/features/identity/api/types";

function formatPermissionLabel(code: string): string {
  return code
    .split(".")
    .map((part) => part.replace(/_/g, " "))
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" → ");
}

function moduleGroup(code: string): string {
  const prefix = code.split(".")[0];
  return prefix.charAt(0).toUpperCase() + prefix.slice(1).replace(/_/g, " ");
}

export default function RoleDetailPage({ params }: { params: Promise<{ roleId: string }> }) {
  const { roleId } = use(params);
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const roleQuery = useQuery({
    queryKey: ["role", companyId, roleId],
    queryFn: () => identityApi.getRole(companyId, roleId),
  });
  const permissionsQuery = useQuery({
    queryKey: ["permissions", companyId],
    queryFn: () => identityApi.listPermissions(companyId),
  });

  if (roleQuery.isError && roleQuery.error instanceof ApiError && roleQuery.error.status === 404) {
    return (
      <SettingsShell>
        <NotFoundState label={t("settings.security.role_not_found")} />
      </SettingsShell>
    );
  }
  if (roleQuery.isError) {
    return (
      <SettingsShell>
        <ErrorState onRetry={() => roleQuery.refetch()} />
      </SettingsShell>
    );
  }
  if (roleQuery.isLoading || !roleQuery.data || permissionsQuery.isLoading || !permissionsQuery.data) {
    return (
      <SettingsShell>
        <Skeleton className="h-96 w-full" />
      </SettingsShell>
    );
  }

  return (
    <SettingsShell>
      <RolePermissionsForm
        key={roleQuery.data.id}
        role={roleQuery.data}
        allPermissions={permissionsQuery.data}
        companyId={companyId}
      />
    </SettingsShell>
  );
}

function RolePermissionsForm({
  role,
  allPermissions,
  companyId,
}: {
  role: { id: string; name: string; is_system: boolean; permission_codes: string[] };
  allPermissions: Permission[];
  companyId: string;
}) {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set(role.permission_codes));
  const [error, setError] = useState<string | null>(null);

  const groups = new Map<string, Permission[]>();
  for (const permission of allPermissions) {
    const group = moduleGroup(permission.code);
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group)!.push(permission);
  }

  function toggle(code: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  const saveMutation = useMutation({
    mutationFn: () => identityApi.updateRolePermissions(companyId, role.id, Array.from(selected)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["role", companyId, role.id] });
      queryClient.invalidateQueries({ queryKey: ["roles", companyId] });
      // The change may affect permissions the *current* logged-in user
      // holds (e.g. granting a role you're a member of) — invalidate
      // broadly so any `<Can>` gate re-evaluates without a full reload.
      queryClient.invalidateQueries({ queryKey: ["me-permissions"] });
      toastSuccess(t("toast.success_title"), t("settings.security.permissions_saved"));
    },
    onError: (err) => {
      const message = err instanceof ApiError ? err.detail : t("common.error");
      setError(message);
      toastError(t("toast.error_title"), message);
    },
  });

  return (
    <FormView
      title={role.name}
      statusBadge={<Badge variant={role.is_system ? "secondary" : "outline"}>{role.is_system ? t("settings.security.system") : t("settings.security.custom")}</Badge>}
      breadcrumbs={[{ label: t("settings.section.security"), href: "/settings/security" }, { label: role.name }]}
      onSave={() => {
        setError(null);
        saveMutation.mutate();
      }}
      onCancel={() => router.push("/settings/security")}
      isSaving={saveMutation.isPending}
      error={error}
    >
      <div className="space-y-5">
        {Array.from(groups.entries())
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([group, permissions]) => (
            <div key={group} className="space-y-2">
              <p className="text-sm font-semibold">{group}</p>
              <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                {permissions.map((permission) => (
                  <label key={permission.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selected.has(permission.code)}
                      onChange={() => toggle(permission.code)}
                    />
                    {formatPermissionLabel(permission.code)}
                  </label>
                ))}
              </div>
            </div>
          ))}
      </div>
    </FormView>
  );
}
