import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output produces the minimal server bundle the Docker image uses
  // (local compose). Vercel builds its own way and errors on standalone's file
  // trace, so skip it there.
  output: process.env.VERCEL ? undefined : "standalone",
  // Allow the dev server to be reached over 127.0.0.1 as well as localhost,
  // which some tooling (Playwright, the preview browser) uses. Dev-only.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
