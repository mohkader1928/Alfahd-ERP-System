"use client";

import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { notificationsApi } from "@/features/notifications/api/client";
import { formatDate } from "@/lib/format-date";

/**
 * Professional Workspace Layer — Notifications. Pairs with the Approval
 * Workflow: an approval request with no way to alert the approver is only
 * half a feature (confirmed missing entirely in the full-system audit that
 * picked this bundle). Polls rather than pushing — no websocket
 * infrastructure exists in this stack yet, and a 30s poll is the same
 * tradeoff every reference ERP's web client makes before investing in a
 * push channel.
 */
export function NotificationBell() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const unreadQuery = useQuery({
    queryKey: ["notifications-unread-count", companyId],
    queryFn: () => notificationsApi.unreadCount(companyId),
    refetchInterval: 30_000,
  });

  const listQuery = useQuery({
    queryKey: ["notifications-list", companyId],
    queryFn: () => notificationsApi.list(companyId),
    refetchInterval: 30_000,
  });

  const unreadCount = unreadQuery.data?.count ?? 0;
  const notifications = listQuery.data ?? [];

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["notifications-unread-count", companyId] });
    queryClient.invalidateQueries({ queryKey: ["notifications-list", companyId] });
  };

  async function handleOpenNotification(notification: (typeof notifications)[number]) {
    if (!notification.is_read) {
      await notificationsApi.markRead(companyId, notification.id);
      invalidate();
    }
    if (notification.link) router.push(notification.link);
  }

  async function handleMarkAllRead() {
    await notificationsApi.markAllRead(companyId);
    invalidate();
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="ghost" size="icon" className="relative" />}>
        <Bell className="h-4 w-4" />
        {unreadCount > 0 && (
          <span className="absolute end-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <div className="flex items-center justify-between px-1.5 py-1">
          <span className="text-xs font-medium text-muted-foreground">{t("notifications.title")}</span>
          {unreadCount > 0 && (
            <button
              type="button"
              onClick={handleMarkAllRead}
              className="text-xs text-primary hover:underline"
            >
              {t("notifications.mark_all_read")}
            </button>
          )}
        </div>
        {notifications.length === 0 && (
          <p className="px-1.5 py-4 text-center text-sm text-muted-foreground">{t("notifications.empty")}</p>
        )}
        {notifications.map((n) => (
          <DropdownMenuItem
            key={n.id}
            onClick={() => handleOpenNotification(n)}
            className="flex-col items-start gap-0.5 whitespace-normal py-2"
          >
            <div className="flex w-full items-center gap-1.5">
              {!n.is_read && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />}
              <span className={n.is_read ? "text-sm text-muted-foreground" : "text-sm font-medium"}>{n.title}</span>
            </div>
            <span className="text-xs text-muted-foreground">{n.body}</span>
            <span className="text-[11px] text-muted-foreground">{formatDate(n.created_at, locale)}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
