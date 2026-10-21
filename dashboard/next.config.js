/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Deploys build a self-contained server in GitHub Actions (NEXT_OUTPUT=standalone)
  // so the server never runs npm ci / next build, which runs it out of memory.
  // Local dev, `next start` and the CI checks keep the default output.
  ...(process.env.NEXT_OUTPUT === 'standalone' ? { output: 'standalone' } : {}),
}

module.exports = nextConfig
