import { identityApi } from "@/features/identity/api/client";
import { firstAuthorizedRoute } from "@/lib/nav-config";

/**
 * Where to send a user right after they get an active company context --
 * called from login and from /select-company instead of both hardcoding
 * "/dashboard". Falls back to "/dashboard" itself (the old, unconditional
 * behavior) if the permissions fetch fails, so a transient network glitch
 * right after login degrades to the previous behavior rather than blocking
 * the redirect entirely.
 */
export async function resolveLandingRoute(companyId: string, branchId: string | null): Promise<string> {
  try {
    const { permission_codes } = await identityApi.getMyPermissions(companyId, branchId);
    return firstAuthorizedRoute(permission_codes);
  } catch {
    return "/dashboard";
  }
}
