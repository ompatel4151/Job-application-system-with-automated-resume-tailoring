import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a minimal self-contained server bundle for a small container image.
  output: "standalone",
  // Allow the dev server to be reached over 127.0.0.1 as well as localhost,
  // which some tooling (Playwright, the preview browser) uses. Dev-only.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
