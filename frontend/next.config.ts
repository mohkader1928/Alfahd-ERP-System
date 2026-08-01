import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output produces a self-contained server bundle (node_modules
  // pruned to only what's traced as actually used) — the production
  // Dockerfile copies just `.next/standalone` + `.next/static`, keeping the
  // image far smaller than shipping the full dev node_modules tree.
  output: "standalone",
};

export default nextConfig;
