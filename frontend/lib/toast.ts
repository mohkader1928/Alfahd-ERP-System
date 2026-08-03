"use client";

import { Toast } from "@base-ui/react/toast";

const { createToastManager } = Toast;

/**
 * UI/UX Foundation milestone: one shared toast manager for the whole app,
 * built on @base-ui/react's own Toast primitive (already a dependency —
 * same library already used for Dialog/Select/Tabs/DropdownMenu, no new
 * package). Exported as a plain module-level singleton (not a hook) so any
 * mutation's onSuccess/onError — most of which live outside a component's
 * render, e.g. in useMutation options — can call toastSuccess/toastError
 * directly without needing to be inside a component that calls
 * useToastManager(). <Toaster/> (components/ui/toast.tsx) renders whatever
 * gets added here; it's mounted once at the app root (app/layout.tsx).
 */
export const toastManager = createToastManager();

export function toastSuccess(title: string, description?: string) {
  toastManager.add({ title, description, type: "success", timeout: 4000 });
}

export function toastError(title: string, description?: string) {
  toastManager.add({ title, description, type: "error", timeout: 6000 });
}
