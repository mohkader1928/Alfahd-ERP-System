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
import type { UserListRow } from "@/features/identity/api/types";

/**
 * Bundle 2 — Identity/Access/Governance. `POST /users` and the role/
 * company-access grant endpoints already existed with zero frontend — an
 * owner could not add a second real employee through the product at all.
 * Mirrors the Roles list/detail pattern (settings/security) exactly, same
 * as every other "list + quick-create dialog + detail page" screen.
 */
export default function UsersSettingsPage() {
  const { t } = useI18n();
  const router = useRouter();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  const usersQuery = useQuery({
    queryKey: ["users", companyId],
    queryFn: () => identityApi.listUsers(companyId),
  });

  const createMutation = useMutation({
    mutationFn: () => identityApi.createUser(companyId, { email, full_name: fullName, password }),
    onSuccess: (user) => {
      queryClient.invalidateQueries({ queryKey: ["users", companyId] });
      toastSuccess(t("toast.success_title"), t("settings.users.user_created"));
      setCreateOpen(false);
      setEmail("");
      setFullName("");
      setPassword("");
      router.push(`/settings/users/${user.id}`);
    },
    onError: (err) => {
      const message = err instanceof ApiError ? err.detail : t("common.error");
      setCreateError(message);
      toastError(t("toast.error_title"), message);
    },
  });

  const columns: ERPColumn<UserListRow>[] = [
    {
      key: "full_name",
      header: t("settings.users.full_name"),
      sortable: true,
      sortValue: (r) => r.full_name,
      render: (r) => (
        <a
          href={`/settings/users/${r.id}`}
          onClick={(e) => {
            e.preventDefault();
            router.push(`/settings/users/${r.id}`);
          }}
          className="font-medium underline-offset-4 hover:underline"
        >
          {r.full_name}
        </a>
      ),
    },
    { key: "email", header: t("settings.users.email"), render: (r) => r.email },
    {
      key: "roles",
      header: t("settings.users.roles"),
      render: (r) =>
        r.role_names.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {r.role_names.map((name) => (
              <Badge key={name} variant="outline">
                {name}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-sm text-muted-foreground">{t("settings.users.no_roles")}</span>
        ),
    },
    {
      key: "is_active",
      header: t("settings.users.status"),
      render: (r) => (
        <Badge variant={r.is_active ? "secondary" : "outline"}>
          {r.is_active ? t("settings.users.active") : t("settings.users.inactive")}
        </Badge>
      ),
    },
  ];

  return (
    <SettingsShell>
      <div className="space-y-3">
        <ERPListView
          title={t("settings.section.users")}
          columns={columns}
          rows={usersQuery.data}
          rowKey={(r) => r.id}
          isLoading={usersQuery.isLoading}
          isError={usersQuery.isError}
          onRetry={() => usersQuery.refetch()}
          searchText={(r) => `${r.full_name} ${r.email}`}
          searchPlaceholder={t("list.search_placeholder")}
          emptyDescription={t("settings.users.empty_description")}
          createAction={{
            label: t("settings.users.new_user"),
            onClick: () => setCreateOpen(true),
            permission: "user.create",
          }}
        />
      </div>

      <Dialog open={createOpen} onOpenChange={(open) => !open && setCreateOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("settings.users.new_user")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>{t("settings.users.full_name")}</Label>
              <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>{t("settings.users.email")}</Label>
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>{t("settings.users.password")}</Label>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
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
              disabled={!email.trim() || !fullName.trim() || !password.trim() || createMutation.isPending}
            >
              {createMutation.isPending ? t("common.loading") : t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SettingsShell>
  );
}
