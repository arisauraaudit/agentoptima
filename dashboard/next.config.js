/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',        // static HTML export
  trailingSlash: true,     // /onboarding/ instead of /onboarding
  images: {
    unoptimized: true,     // required for static export
  },
}

module.exports = nextConfig
