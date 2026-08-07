import { apiClient } from "@/lib/api-client";
import type { Attachment } from "./types";

const BASE = "/api/v1/attachments";

export const attachmentsApi = {
  list: (companyId: string, entityType: string, entityId: string) =>
    apiClient.get<Attachment[]>(
      `${BASE}?entity_type=${encodeURIComponent(entityType)}&entity_id=${entityId}`,
      { companyId }
    ),

  upload: (companyId: string, entityType: string, entityId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiClient.post<Attachment>(
      `${BASE}?entity_type=${encodeURIComponent(entityType)}&entity_id=${entityId}`,
      formData,
      { companyId }
    );
  },

  remove: (companyId: string, attachmentId: string) =>
    apiClient.delete<void>(`${BASE}/${attachmentId}`, { companyId }),

  download: async (companyId: string, attachmentId: string) => {
    const { blob, filename } = await apiClient.getBlob(`${BASE}/${attachmentId}/download`, { companyId });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};
