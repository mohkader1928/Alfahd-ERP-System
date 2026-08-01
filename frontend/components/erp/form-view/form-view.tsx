"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Breadcrumbs, type BreadcrumbItem } from "@/components/erp/breadcrumbs/breadcrumbs";
import { useI18n } from "@/lib/i18n/config";

interface FormViewProps {
  title: string;
  breadcrumbs?: BreadcrumbItem[];
  statusBadge?: React.ReactNode;
  primaryActions?: React.ReactNode;
  secondaryActions?: React.ReactNode;
  children: React.ReactNode;
  onSave?: () => void;
  onCancel?: () => void;
  saveLabel?: string;
  cancelLabel?: string;
  isSaving?: boolean;
  saveDisabled?: boolean;
  error?: string | null;
  footerExtra?: React.ReactNode;
}

/**
 * Phase 17A shared ERP form shell (Part 6): header (breadcrumb, title,
 * status, actions) / body (caller-supplied sections or tabs as `children`)
 * / footer (Save/Cancel). Field-level layout stays with each form — this
 * only standardizes the chrome around it, per Part 6's "establish the
 * reusable architecture, don't redesign business forms yet."
 */
export function FormView({
  title,
  breadcrumbs,
  statusBadge,
  primaryActions,
  secondaryActions,
  children,
  onSave,
  onCancel,
  saveLabel,
  cancelLabel,
  isSaving,
  saveDisabled,
  error,
  footerExtra,
}: FormViewProps) {
  const { t } = useI18n();

  return (
    <div className="space-y-4">
      {breadcrumbs && <Breadcrumbs items={breadcrumbs} />}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold">{title}</h1>
          {statusBadge}
        </div>
        <div className="flex items-center gap-2">
          {secondaryActions}
          {primaryActions}
        </div>
      </div>

      <Card>
        <CardContent className="space-y-4 pt-4">{children}</CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {(onSave || onCancel) && (
        <div className="flex items-center justify-end gap-2">
          {footerExtra}
          {onCancel && (
            <Button variant="outline" onClick={onCancel} disabled={isSaving}>
              {cancelLabel ?? t("common.cancel")}
            </Button>
          )}
          {onSave && (
            <Button onClick={onSave} disabled={isSaving || saveDisabled}>
              {isSaving ? t("common.loading") : (saveLabel ?? t("common.save"))}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
