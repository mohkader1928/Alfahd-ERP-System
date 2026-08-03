/**
 * Base fetch wrapper (Phase 9 §3): injects the JWT + X-Company-Id/X-Branch-Id
 * headers per Phase 10 §2, and normalizes the backend's RFC 7807 Problem
 * Details error format into a typed ApiError.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
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

export const apiClient = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "DELETE" }),
};
