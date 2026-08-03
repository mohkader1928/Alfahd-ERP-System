"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SettingsShell } from "@/components/erp/settings-shell/settings-shell";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { ApiError } from "@/lib/api-client";
import { toastError, toastSuccess } from "@/lib/toast";
import type { Role } from "@/features/identity/api/types";

/**
 * Settings Architecture Foundation milestone — Security section. The fix
 * for a real, previously-documented gap: a role's permissions used to be
 * fixed at creation time (bootstrap/company-create) with no API to change
 * them afterwards. This screen is that API's UI: list roles, create a new
 * one, click through to edit any role's permission set live.
 */
export default function SecuritySettingsPage() {
  const { t } = useI18n();
  const router = useRouter();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [newRoleName, setNewRoleName] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  const rolesQuery = useQuery({
    queryKey: ["roles", companyId],
    queryFn: () => identityApi.listRoles(companyId),
  });

  const createMutation = useMutation({
    mutationFn: () => identityApi.createRole(companyId, newRoleName),
    onSuccess: (role) => {
      queryClient.invalidateQueries({ queryKey: ["roles", companyId] });
      toastSuccess(t("toast.success_title"), t("settings.security.role_created"));
      setCreateOpen(false);
      setNewRoleName("");
      router.push(`/settings/security/${role.id}`);
    },
    onError: (err) => {
      const message = err instanceof ApiError ? err.detail : t("common.error");
      setCreateError(message);
      toastError(t("toast.error_title"), message);
    },
  });

  const columns: ERPColumn<Role>[] = [
    {
      key: "name",
      header: t("settings.security.role_name"),
      sortable: true,
      sortValue: (r) => r.name,
      render: (r) => (
        <a
          href={`/settings/security/${r.id}`}
          onClick={(e) => {
            e.preventDefault();
            router.push(`/settings/security/${r.id}`);
          }}
          className="font-medium underline-offset-4 hover:underline"
        >
          {r.name}
        </a>
      ),
    },
    {
      key: "is_system",
      header: t("settings.security.role_type"),
      render: (r) => <Badge variant={r.is_system ? "secondary" : "outline"}>{r.is_system ? t("settings.security.system") : t("settings.security.custom")}</Badge>,
    },
  ];

  return (
    <SettingsShell>
      <div className="space-y-3">
        <ERPListView
          title={t("settings.section.security")}
          columns={columns}
          rows={rolesQuery.data}
          rowKey={(r) => r.id}
          isLoading={rolesQuery.isLoading}
          isError={rolesQuery.isError}
          onRetry={() => rolesQuery.refetch()}
          searchText={(r) => r.name}
          searchPlaceholder={t("list.search_placeholder")}
          emptyDescription={t("settings.security.empty_description")}
          createAction={{
            label: t("settings.security.new_role"),
            onClick: () => setCreateOpen(true),
            permission: "role.manage",
          }}
        />
      </div>

      <Dialog open={createOpen} onOpenChange={(open) => !open && setCreateOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("settings.security.new_role")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>{t("settings.security.role_name")}</Label>
              <Input value={newRoleName} onChange={(e) => setNewRoleName(e.target.value)} />
            </div>
            {createError && <p className="text-sm text-destructive">{createError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} disabled={createMutation.isPending}>
              {t("common.cancel")}
            </Button>
            <Button
              onClick={() => {
                setCreateError(null);
                createMutation.mutate();
              }}
              disabled={!newRoleName.trim() || createMutation.isPending}
            >
              {createMutation.isPending ? t("common.loading") : t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SettingsShell>
  );
}
