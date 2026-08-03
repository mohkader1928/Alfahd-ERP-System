"use client";

import { Toast as ToastPrimitive } from "@base-ui/react/toast";
import { CheckCircle2, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { toastManager } from "@/lib/toast";

function ToastList() {
  const { toasts } = ToastPrimitive.useToastManager();

  return (
    <>
      {toasts.map((toast) => (
        <ToastPrimitive.Root
          key={toast.id}
          toast={toast}
          className={cn(
            "pointer-events-auto w-80 rounded-lg border bg-card p-3 text-card-foreground shadow-lg transition-opacity",
            toast.type === "error" ? "border-destructive/30" : "border-border"
          )}
        >
          <div className="flex items-start gap-2">
            {toast.type === "error" ? (
              <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            ) : (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-600 dark:text-green-500" />
            )}
            <div className="flex-1 space-y-0.5">
              <ToastPrimitive.Title className="text-sm font-medium" />
              {toast.description && (
                <ToastPrimitive.Description className="text-xs text-muted-foreground" />
              )}
            </div>
            <ToastPrimitive.Close className="shrink-0 text-muted-foreground hover:text-foreground">
              <X className="h-3.5 w-3.5" />
              <span className="sr-only">Close</span>
            </ToastPrimitive.Close>
          </div>
        </ToastPrimitive.Root>
      ))}
    </>
  );
}

/**
 * Mounted once at the app root (app/layout.tsx). Uses the shared
 * `toastManager` singleton (lib/toast.ts) so toastSuccess()/toastError()
 * work from anywhere — mutation onSuccess/onError handlers, not just
 * component bodies.
 */
export function Toaster() {
  return (
    <ToastPrimitive.Provider toastManager={toastManager}>
      <ToastPrimitive.Portal>
        <ToastPrimitive.Viewport className="fixed bottom-4 end-4 z-50 flex w-80 flex-col gap-2">
          <ToastList />
        </ToastPrimitive.Viewport>
      </ToastPrimitive.Portal>
    </ToastPrimitive.Provider>
  );
}
