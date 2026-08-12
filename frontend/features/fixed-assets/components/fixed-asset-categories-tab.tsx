"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, FolderTree, Pencil, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CategorySelect } from "@/components/erp/category-select/category-select";
import { ConfirmDialog } from "@/components/erp/states/confirm-dialog";
import { EmptyState } from "@/components/erp/states/empty-state";
import { ErrorState } from "@/components/erp/states/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Can } from "@/components/erp/permissions/can";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { fixedAssetsApi } from "@/features/fixed-assets/api/client";
import type { FixedAssetCategory } from "@/features/fixed-assets/api/types";
import { ApiError } from "@/lib/api-client";

/** Mirrors master-data/categories/page.tsx exactly (ProductCategory tree
 * screen) — same tree-builder shape, reused here for Fixed Asset
 * categories so "run depreciation for a specific group" has something
 * real to group assets by. */
interface TreeNode {
  category: FixedAssetCategory;
  children: TreeNode[];
}

function buildTree(categories: FixedAssetCategory[]): TreeNode[] {
  const byParent = new Map<string | null, FixedAssetCategory[]>();
  for (const c of categories) {
    const list = byParent.get(c.parent_id) ?? [];
    list.push(c);
    byParent.set(c.parent_id, list);
  }
  for (const list of byParent.values()) list.sort((a, b) => a.name.localeCompare(b.name));

  function attach(parentId: string | null): TreeNode[] {
    return (byParent.get(parentId) ?? []).map((category) => ({
      category,
      children: attach(category.id),
    }));
  }
  return attach(null);
}

export function FixedAssetCategoriesTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();

  const categoriesQuery = useQuery({
    queryKey: ["fixed-asset-categories", companyId],
    queryFn: () => fixedAssetsApi.listCategories(companyId),
  });

  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [dialogState, setDialogState] = useState<{ mode: "create" | "edit"; category?: FixedAssetCategory; parentId: string | null } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<FixedAssetCategory | null>(null);
  const [formName, setFormName] = useState("");
  const [formParentId, setFormParentId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function openCreate(parentId: string | null) {
    setFormName("");
    setFormParentId(parentId);
    setFormError(null);
    setDialogState({ mode: "create", parentId });
  }

  function openEdit(category: FixedAssetCategory) {
    setFormName(category.name);
    setFormParentId(category.parent_id);
    setFormError(null);
    setDialogState({ mode: "edit", category, parentId: category.parent_id });
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!dialogState) return;
      if (dialogState.mode === "create") {
        return fixedAssetsApi.createCategory(companyId, { name: formName, parent_id: formParentId });
      }
      return fixedAssetsApi.updateCategory(companyId, dialogState.category!.id, {
        name: formName,
        parent_id: formParentId,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["fixed-asset-categories", companyId] });
      setDialogState(null);
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  const deleteMutation = useMutation({
    mutationFn: () => fixedAssetsApi.deleteCategory(companyId, deleteTarget!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["fixed-asset-categories", companyId] });
      setDeleteTarget(null);
    },
    onError: (err) => setDeleteError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function renderNode(node: TreeNode, depth: number) {
    const hasChildren = node.children.length > 0;
    const isOpen = expanded.has(node.category.id);
    return (
      <div key={node.category.id}>
        <div
          className="group flex items-center gap-1 rounded-md py-1.5 hover:bg-muted/50"
          style={{ paddingInlineStart: `${depth * 20}px` }}
        >
          {hasChildren ? (
            <button type="button" onClick={() => toggle(node.category.id)} className="flex h-5 w-5 items-center justify-center text-muted-foreground">
              {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            </button>
          ) : (
            <span className="h-5 w-5" />
          )}
          <FolderTree className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="flex-1 text-sm">{node.category.name}</span>
          <Can permission="fixed_assets.category.manage">
            <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
              <Button variant="ghost" size="icon-xs" title={t("master_data.category.add_child")} onClick={() => openCreate(node.category.id)}>
                <Plus className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon-xs" title={t("common.edit")} onClick={() => openEdit(node.category)}>
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon-xs"
                title={t("common.delete")}
                onClick={() => {
                  setDeleteError(null);
                  setDeleteTarget(node.category);
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </Can>
        </div>
        {hasChildren && isOpen && node.children.map((child) => renderNode(child, depth + 1))}
      </div>
    );
  }

  const tree = buildTree(categoriesQuery.data ?? []);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t("fixed_assets.categories.title")}</h1>
        <Can permission="fixed_assets.category.manage">
          <Button size="sm" onClick={() => openCreate(null)}>
            <Plus className="h-4 w-4" />
            {t("fixed_assets.categories.new_root")}
          </Button>
        </Can>
      </div>

      <Card>
        <CardContent className="pt-4">
          {categoriesQuery.isLoading && <Skeleton className="h-40 w-full" />}
          {categoriesQuery.isError && <ErrorState onRetry={() => categoriesQuery.refetch()} />}
          {!categoriesQuery.isLoading && !categoriesQuery.isError && tree.length === 0 && (
            <EmptyState
              icon={FolderTree}
              title={t("fixed_assets.categories.empty_title")}
              description={t("fixed_assets.categories.empty_description")}
            />
          )}
          {!categoriesQuery.isLoading && !categoriesQuery.isError && tree.length > 0 && (
            <div>{tree.map((node) => renderNode(node, 0))}</div>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogState !== null} onOpenChange={(open) => !open && setDialogState(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {dialogState?.mode === "create" ? t("fixed_assets.categories.new") : t("fixed_assets.categories.edit")}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>{t("fixed_assets.categories.name")}</Label>
              <Input value={formName} onChange={(e) => setFormName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>{t("fixed_assets.categories.parent")}</Label>
              <CategorySelect
                categories={categoriesQuery.data ?? []}
                value={formParentId}
                onChange={setFormParentId}
                excludeId={dialogState?.mode === "edit" ? dialogState.category?.id : undefined}
              />
            </div>
            {formError && <p className="text-sm text-destructive">{formError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogState(null)} disabled={saveMutation.isPending}>
              {t("common.cancel")}
            </Button>
            <Button
              onClick={() => {
                setFormError(null);
                saveMutation.mutate();
              }}
              disabled={!formName.trim() || saveMutation.isPending}
            >
              {saveMutation.isPending ? t("common.loading") : t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={t("fixed_assets.categories.delete_title")}
        description={deleteError ?? t("fixed_assets.categories.delete_description").replace("{name}", deleteTarget?.name ?? "")}
        variant="destructive"
        confirmLabel={t("common.delete")}
        onConfirm={() => deleteMutation.mutate()}
        isPending={deleteMutation.isPending}
      />
    </div>
  );
}
