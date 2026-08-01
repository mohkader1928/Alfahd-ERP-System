/** Decodes the JWT payload client-side to read `authorized_companies`
 * (Phase 10 §2) — no separate "list my companies" endpoint exists, and the
 * claim is already exactly what the UI needs to pick an active company.
 * This does NOT verify the signature (the backend already did); it's read
 * for UI convenience only, never trusted for authorization decisions.
 */
export interface DecodedAccessToken {
  sub: string;
  tenant_id: string;
  authorized_companies: string[];
  exp: number;
}

export function decodeAccessToken(token: string): DecodedAccessToken | null {
  try {
    const [, payload] = token.split(".");
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

export function firstAuthorizedCompany(token: string): { companyId: string; branchId: string | null } | null {
  const decoded = decodeAccessToken(token);
  const entry = decoded?.authorized_companies?.[0];
  if (!entry) return null;
  const [companyId, branchId] = entry.split(":");
  return { companyId, branchId: branchId ?? null };
}
