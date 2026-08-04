/** @type {import('next').NextConfig} */
const BACKEND = process.env.POC_BACKEND || "http://127.0.0.1:8765";

const nextConfig = {
  reactStrictMode: true,
  // Server-side proxy to the verify_app backend so the browser never makes a
  // cross-origin call (verify_app sends no CORS headers). Set POC_BACKEND to the
  // deployed verify_app URL in production.
  async rewrites() {
    return [{ source: "/poc-api/:path*", destination: `${BACKEND}/api/:path*` }];
  },
};

module.exports = nextConfig;
