import { apiClient } from "@/lib/api-client";
import type { NotificationRow } from "./types";

const BASE = "/api/v1";

export const notificationsApi = {
  list: (companyId: string, unreadOnly = false) =>
    apiClient.get<NotificationRow[]>(`${BASE}/notifications?unread_only=${unreadOnly}`, { companyId }),

  unreadCount: (companyId: string) =>
    apiClient.get<{ count: number }>(`${BASE}/notifications/unread-count`, { companyId }),

  markRead: (companyId: string, notificationId: string) =>
    apiClient.post<NotificationRow>(`${BASE}/notifications/${notificationId}:read`, undefined, { companyId }),

  markAllRead: (companyId: string) =>
    apiClient.post<void>(`${BASE}/notifications:read-all`, undefined, { companyId }),
};
