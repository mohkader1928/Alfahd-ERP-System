"use client";

import { useState } from "react";
import { Image as ImageIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { mediaUrl } from "@/lib/media";
import { Skeleton } from "@/components/ui/skeleton";

const SIZE_CLASSES = {
  xs: "h-6 w-6 text-[10px]",
  sm: "h-8 w-8 text-xs",
  md: "h-10 w-10 text-sm",
  lg: "h-16 w-16 text-lg",
  xl: "h-24 w-24 text-2xl",
} as const;

export type EntityImageSize = keyof typeof SIZE_CLASSES;

function initialsFrom(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "";
  const parts = trimmed.split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "";
  const second = parts.length > 1 ? (parts[1]?.[0] ?? "") : "";
  return (first + second).toUpperCase();
}

export interface EntityImageProps {
  /** Relative path from the backend (e.g. "company/<uuid>/<uuid>.png"), or
   * null/undefined when the entity has no image yet. */
  src?: string | null;
  /** Used for the initials fallback and as the default alt text. */
  name: string;
  alt?: string;
  size?: EntityImageSize;
  shape?: "circle" | "square";
  isLoading?: boolean;
  className?: string;
}

/**
 * UI/UX Evolution milestone — Entity Media Foundation. One shared
 * image/logo/avatar display for Company logos, Customer/Vendor images,
 * and Product images — not four separate implementations (see
 * docs/18-ui-ux-audit.md's "fix the shared component once" rule). Handles
 * every state itself: real image, initials fallback, empty placeholder,
 * loading, and a broken/failed image link (falls back to initials rather
 * than a broken-image icon). No inherent start/end assumptions — a plain
 * centered box, safe to compose with flex+gap in either text direction.
 */
export function EntityImage({ src, name, alt, size = "md", shape = "circle", isLoading = false, className }: EntityImageProps) {
  const url = mediaUrl(src);
  const [failed, setFailed] = useState(false);
  const [lastUrl, setLastUrl] = useState(url);

  // Derived-state reset, not an effect: a new src (e.g. right after an
  // upload replaces the image) must get a fresh chance to load rather than
  // staying stuck on a previous failure. Computed directly during render —
  // React's documented pattern for "adjusting state when a prop changes" —
  // matching this codebase's existing use of the same pattern (see
  // lib/i18n/config.tsx's set-state-in-effect note).
  if (url !== lastUrl) {
    setLastUrl(url);
    setFailed(false);
  }

  const sizeClass = SIZE_CLASSES[size];
  const shapeClass = shape === "circle" ? "rounded-full" : "rounded-md";

  if (isLoading) {
    return <Skeleton className={cn(sizeClass, shapeClass, className)} />;
  }

  if (url && !failed) {
    return (
      // Deliberately a plain <img>, not next/image: the source is
      // self-hosted at an unpredictable size (see backend's /media mount),
      // and no other screen in this app uses next/image either
      // (docs/18-ui-ux-audit.md — not introducing a second image-loading
      // pattern for this alone).
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={url}
        alt={alt ?? name}
        onError={() => setFailed(true)}
        className={cn(sizeClass, shapeClass, "shrink-0 object-cover", className)}
      />
    );
  }

  const initials = initialsFrom(name);

  return (
    <div
      role="img"
      aria-label={alt ?? name}
      className={cn(
        sizeClass,
        shapeClass,
        "flex shrink-0 items-center justify-center bg-muted font-medium text-muted-foreground",
        className
      )}
    >
      {initials || <ImageIcon className="h-1/2 w-1/2 opacity-50" />}
    </div>
  );
}
