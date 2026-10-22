import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  /* config options here */
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // Reverse proxy API requests to the Python FastAPI backend:
  // 1. Avoids CORS issues because the browser only communicates with localhost:3000.
  // 2. Seamlessly routes any request to /api/* to the Python server (default: localhost:8000).
  async rewrites() {
    return [
      {
        // Incoming route pattern to intercept:
        // matches any request starting with /api/ and captures the rest via :path*
        source: "/api/:path*",
        // forward all API requests to the Python FastAPI backend
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
