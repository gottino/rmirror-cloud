const { buildSecurityHeaders } = require('./lib/csp')

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Deploys build a self-contained server in GitHub Actions (NEXT_OUTPUT=standalone)
  // so the server never runs npm ci / next build, which runs it out of memory.
  // Local dev, `next start` and the CI checks keep the default output.
  ...(process.env.NEXT_OUTPUT === 'standalone' ? { output: 'standalone' } : {}),
  // Evaluated at build time and baked into the build (standalone included).
  // The CSP is Report-Only unless the build runs with CSP_ENFORCE=true; see lib/csp.js.
  async headers() {
    return [{ source: '/:path*', headers: buildSecurityHeaders(process.env) }]
  },
}

module.exports = nextConfig
