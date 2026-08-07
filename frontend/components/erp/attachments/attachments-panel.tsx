"use client";

import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileSpreadsheet, FileText, Image as ImageIcon, Paperclip, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Can } from "@/components/erp/permissions/can";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { attachmentsApi } from "@/features/attachments/api/client";
import { ApiError } from "@/lib/api-client";
import { formatDate } from "@/lib/format-date";
import { toastError } from "@/lib/toast";

const ALLOWED_TYPES =
  "application/pdf,image/jpeg,image/png,image/webp,application/msword," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
  "application/vnd.ms-excel," +
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet," +
  "text/csv,text/plain";
const MAX_BYTES = 10 * 1024 * 1024;

function fileIcon(contentType: string) {
  if (contentType.startsWith("image/")) return ImageIcon;
  if (contentType.includes("sheet") || contentType.includes("excel") || contentType === "text/csv") {
    return FileSpreadsheet;
  }
  return FileText;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Professional Workspace Layer — Attachments. One shared panel reused on
 * every document detail page (sales invoices, purchase orders, vendor
 * bills, ...) instead of each screen building its own upload/list/delete
 * UI — same "fix the shared component once" rule Entity Media Foundation
 * already established for images.
 */
export function AttachmentsPanel({ entityType, entityId }: { entityType: string; entityId: string }) {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const queryKey = ["attachments", companyId, entityType, entityId];

  const listQuery = useQuery({
    queryKey,
    queryFn: () => attachmentsApi.list(companyId, entityType, entityId),
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => attachmentsApi.upload(companyId, entityType, entityId, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  const deleteMutation = useMutation({
    mutationFn: (attachmentId: string) => attachmentsApi.remove(companyId, attachmentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > MAX_BYTES) {
      toastError(t("toast.error_title"), t("attachments.too_large"));
      return;
    }
    uploadMutation.mutate(file);
  }

  return (
    <div className="space-y-2 border-t pt-4">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-sm font-medium">
          <Paperclip className="h-4 w-4" />
          {t("attachments.title")}
        </p>
        <Can permission="attachment.manage">
          <input
            ref={inputRef}
            type="file"
            accept={ALLOWED_TYPES}
            className="hidden"
            onChange={handleFileChange}
            disabled={uploadMutation.isPending}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={uploadMutation.isPending}
          >
            <Upload className="h-4 w-4" />
            {uploadMutation.isPending ? t("common.loading") : t("attachments.upload")}
          </Button>
        </Can>
      </div>

      {listQuery.isLoading && <Skeleton className="h-10 w-full" />}
      {!listQuery.isLoading && (listQuery.data?.length ?? 0) === 0 && (
        <p className="text-sm text-muted-foreground">{t("attachments.empty")}</p>
      )}
      {!listQuery.isLoading && listQuery.data && listQuery.data.length > 0 && (
        <ul className="space-y-1.5">
          {listQuery.data.map((attachment) => {
            const Icon = fileIcon(attachment.content_type);
            return (
              <li
                key={attachment.id}
                className="flex items-center justify-between gap-2 rounded-md border px-2.5 py-1.5 text-sm"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0">
                    <p className="truncate font-medium">{attachment.original_filename}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatFileSize(attachment.file_size)} · {attachment.uploaded_by_name} ·{" "}
                      {formatDate(attachment.uploaded_at, locale)}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => attachmentsApi.download(companyId, attachment.id)}
                    title={t("attachments.download")}
                  >
                    <Download className="h-3.5 w-3.5" />
                  </Button>
                  <Can permission="attachment.manage">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => deleteMutation.mutate(attachment.id)}
                      disabled={deleteMutation.isPending}
                      title={t("attachments.delete")}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </Can>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
