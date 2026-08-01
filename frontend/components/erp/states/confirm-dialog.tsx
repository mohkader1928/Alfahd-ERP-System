"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n/config";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  variant?: "default" | "destructive";
  confirmLabel?: string;
  onConfirm: () => void;
  isPending?: boolean;
}

/**
 * Phase 17A standard confirmation pattern (Part 13) — used for both plain
 * confirmations and destructive-action ("delete this?") confirmations via
 * `variant`. Every future ERP screen should reuse this instead of a
 * bespoke window.confirm() or one-off dialog.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  variant = "default",
  confirmLabel,
  onConfirm,
  isPending,
}: ConfirmDialogProps) {
  const { t } = useI18n();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
            {t("common.cancel")}
          </Button>
          <Button
            variant={variant === "destructive" ? "destructive" : "default"}
            onClick={onConfirm}
            disabled={isPending}
          >
            {isPending ? t("common.loading") : (confirmLabel ?? t("common.confirm"))}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
