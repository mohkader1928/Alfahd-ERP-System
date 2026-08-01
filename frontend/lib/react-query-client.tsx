"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError } from "./api-client";

function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
    return false; // don't retry client errors (401/403/404/422) — only transient/server failures
  }
  return failureCount < 2;
}

export function ReactQueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: shouldRetry, staleTime: 30_000 },
          mutations: { retry: false },
        },
      })
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
