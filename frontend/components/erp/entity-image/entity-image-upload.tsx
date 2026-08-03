"use client";

import { useRef } from "react";
import { Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/config";
import { toastError } from "@/lib/toast";
import { EntityImage, type EntityImageSize } from "./entity-image";

const ALLOWED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const MAX_BYTES = 2 * 1024 * 1024;

export interface EntityImageUploadProps {
  src?: string | null;
  name: string;
  size?: EntityImageSize;
  shape?: "circle" | "square";
  onUpload: (file: File) => void;
  onRemove?: () => void;
  isUploading?: boolean;
  isRemoving?: boolean;
  disabled?: boolean;
}

/**
 * UI/UX Evolution milestone — Entity Media Foundation. The create/edit-form
 * counterpart to EntityImage: same display, plus a file picker and a
 * remove action. Upload/remove side effects are left to the caller (each
 * entity type calls a different endpoint) — this component only picks and
 * client-side-validates the file, matching the backend's own limits
 * (backend/src/shared/media/storage.py) so a bad file is rejected
 * instantly instead of round-tripping to the server first.
 */
export function EntityImageUpload({
  src,
  name,
  size = "lg",
  shape = "circle",
  onUpload,
  onRemove,
  isUploading = false,
  isRemoving = false,
  disabled = false,
}: EntityImageUploadProps) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!ALLOWED_TYPES.has(file.type)) {
      toastError(t("toast.error_title"), t("media.invalid_type"));
      return;
    }
    if (file.size > MAX_BYTES) {
      toastError(t("toast.error_title"), t("media.too_large"));
      return;
    }
    onUpload(file);
  }

  return (
    <div className="flex items-center gap-3">
      <EntityImage src={src} name={name} size={size} shape={shape} isLoading={isUploading} />
      <div className="flex flex-col gap-1.5">
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={handleFileChange}
          disabled={disabled || isUploading || isRemoving}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => inputRef.current?.click()}
          disabled={disabled || isUploading || isRemoving}
        >
          <Upload className="h-4 w-4" />
          {isUploading ? t("common.loading") : src ? t("media.change") : t("media.upload")}
        </Button>
        {src && onRemove && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onRemove}
            disabled={disabled || isUploading || isRemoving}
          >
            <X className="h-4 w-4" />
            {isRemoving ? t("common.loading") : t("media.remove")}
          </Button>
        )}
      </div>
    </div>
  );
}
