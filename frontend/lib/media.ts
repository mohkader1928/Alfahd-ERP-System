/**
 * UI/UX Evolution milestone — Entity Media Foundation. Backend stores and
 * returns a relative path only (e.g. "company/<uuid>/<uuid>.png", see
 * backend/src/shared/media/storage.py); this is the one place that turns
 * it into a URL an <img> can load, mirroring how api-client.ts is the one
 * place that knows the API's base URL.
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function mediaUrl(relativePath: string | null | undefined): string | null {
  if (!relativePath) return null;
  return `${API_BASE_URL}/media/${relativePath}`;
}
