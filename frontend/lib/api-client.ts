/**
 * Base fetch wrapper (Phase 9 §3): injects the JWT + X-Company-Id/X-Branch-Id
 * headers per Phase 10 §2, and normalizes the backend's RFC 7807 Problem
 * Details error format into a typed ApiError.
 */

import { useAuthStore } from "@/stores/auth-store";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const REFRESH_PATH = "/api/v1/identity/auth/refresh";

export class ApiError extends Error {
  status: number;
  detail: string;
  fieldErrors: { field: string; message: string }[];

  constructor(status: number, title: string, detail: string, fieldErrors: { field: string; message: string }[] = []) {
    super(detail || title);
    this.status = status;
    this.detail = detail || title;
    this.fieldErrors = fieldErrors;
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  companyId?: string | null;
  branchId?: string | null;
  skipAuth?: boolean;
}

function getStoredAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("erp.access_token");
}

// Owner-reported bug: the 30-minute access token had no renewal path at
// all, so leaving the app idle for a bit over that killed every request
// with a 401 and the only recovery was a full manual logout/login. A
// single in-flight refresh (deduped via this module-level promise, so N
// requests failing at once trigger one /auth/refresh call, not N) lets
// any 401 silently mint a fresh token and retry once, invisibly to the
// caller — logout only happens if the refresh token itself is dead too.
let refreshPromise: Promise<void> | null = null;

async function ensureFreshAccessToken(): Promise<void> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const currentRefreshToken = useAuthStore.getState().refreshToken;
      if (!currentRefreshToken) throw new Error("No refresh token available");

      const response = await fetch(`${API_BASE_URL}${REFRESH_PATH}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: currentRefreshToken }),
      });
      if (!response.ok) throw new Error("Refresh token rejected");

      const tokens = (await response.json()) as { access_token: string; refresh_token: string };
      useAuthStore.getState().setTokens(tokens.access_token, tokens.refresh_token);
    })().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

async function request<T>(path: string, options: RequestOptions = {}, isRetry = false): Promise<T> {
  const { body, companyId, branchId, skipAuth, headers, ...rest } = options;

  // FormData (file uploads) must NOT get a manual Content-Type: the browser
  // sets its own multipart boundary, which JSON.stringify-ing the body (and
  // forcing application/json below) would break.
  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;

  const finalHeaders: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(headers as Record<string, string> | undefined),
  };

  if (!skipAuth) {
    const token = getStoredAccessToken();
    if (token) finalHeaders["Authorization"] = `Bearer ${token}`;
  }
  if (companyId) finalHeaders["X-Company-Id"] = companyId;
  if (branchId) finalHeaders["X-Branch-Id"] = branchId;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: finalHeaders,
    body: isFormData ? (body as FormData) : body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (response.status === 204) {
    return undefined as T;
  }

  if (response.status === 401 && !skipAuth && !isRetry && path !== REFRESH_PATH) {
    try {
      await ensureFreshAccessToken();
      return request<T>(path, options, true);
    } catch {
      useAuthStore.getState().logout();
      if (typeof window !== "undefined") window.location.href = "/login";
    }
  }

  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    if (isJson && payload && typeof payload === "object") {
      throw new ApiError(
        response.status,
        payload.title ?? "Error",
        payload.detail ?? "Request failed",
        payload.errors ?? []
      );
    }
    throw new ApiError(response.status, "Error", typeof payload === "string" ? payload : "Request failed");
  }

  // Backend envelope is either a bare object/array or a resource straight
  // from a response_model — the nucleus API doesn't wrap list/detail
  // responses in {data: ...}, so we return the parsed payload as-is.
  return payload as T;
}

async function requestBlob(
  path: string,
  options: Omit<RequestOptions, "body"> = {},
  isRetry = false
): Promise<{ blob: Blob; filename: string }> {
  const { companyId, branchId, skipAuth, headers, ...rest } = options;
  const finalHeaders: Record<string, string> = { ...(headers as Record<string, string> | undefined) };
  if (!skipAuth) {
    const token = getStoredAccessToken();
    if (token) finalHeaders["Authorization"] = `Bearer ${token}`;
  }
  if (companyId) finalHeaders["X-Company-Id"] = companyId;
  if (branchId) finalHeaders["X-Branch-Id"] = branchId;

  const response = await fetch(`${API_BASE_URL}${path}`, { ...rest, headers: finalHeaders });

  if (response.status === 401 && !skipAuth && !isRetry) {
    try {
      await ensureFreshAccessToken();
      return requestBlob(path, options, true);
    } catch {
      useAuthStore.getState().logout();
      if (typeof window !== "undefined") window.location.href = "/login";
    }
  }

  if (!response.ok) {
    const isJson = response.headers.get("content-type")?.includes("application/json");
    const payload = isJson ? await response.json() : await response.text();
    if (isJson && payload && typeof payload === "object") {
      throw new ApiError(response.status, payload.title ?? "Error", payload.detail ?? "Request failed");
    }
    throw new ApiError(response.status, "Error", typeof payload === "string" ? payload : "Request failed");
  }

  const disposition = response.headers.get("content-disposition") ?? "";
  const filename = disposition.match(/filename="?([^"]+)"?/)?.[1] ?? "report";
  return { blob: await response.blob(), filename };
}

export const apiClient = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PUT", body }),
  delete: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "DELETE" }),
  getBlob: (path: string, options?: RequestOptions) => requestBlob(path, { ...options, method: "GET" }),
};
