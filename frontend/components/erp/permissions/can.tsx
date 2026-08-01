"use client";

import { useMyPermissions } from "@/hooks/use-permissions";

interface CanProps {
  /** A single permission code, or a list where any one grants access. */
  permission: string | string[];
  children: React.ReactNode;
  /** Rendered instead of nothing while permitted=false. Omit to just hide. */
  fallback?: React.ReactNode;
}

/**
 * Phase 17A permission-aware UI gate (Part 16). Hides `children` until the
 * caller's permissions are known AND include the required code(s) — never
 * flashes a forbidden action while loading. This is presentation only: the
 * backend's `require_permission()` dependency remains the actual security
 * boundary, so hiding here is a UX courtesy, not a defense.
 */
export function Can({ permission, children, fallback = null }: CanProps) {
  const { can, canAny, isLoading } = useMyPermissions();

  if (isLoading) return <>{fallback}</>;

  const permitted = Array.isArray(permission) ? canAny(permission) : can(permission);
  return <>{permitted ? children : fallback}</>;
}
