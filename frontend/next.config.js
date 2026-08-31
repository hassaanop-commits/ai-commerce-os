/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Keeps the browser talking to a single origin: Next.js proxies
    // /api/v1/* straight through to FastAPI. That's what makes the session
    // and CSRF cookies same-origin (no CORS, no cross-site cookie rules) for
    // every client-side fetch. Server-side fetches (lib/server-api.ts) call
    // the backend directly instead, since they're not subject to browser
    // same-origin rules to begin with.
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
