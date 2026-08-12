"use client";

import { useSearchParams } from "next/navigation";
import { FixedAssetCardTab } from "@/features/fixed-assets/components/fixed-asset-card-tab";

export default function FixedAssetCardPage() {
  const searchParams = useSearchParams();
  const initialAssetId = searchParams.get("asset") ?? undefined;
  return <FixedAssetCardTab initialAssetId={initialAssetId} />;
}
