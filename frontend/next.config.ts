import type { NextConfig } from "next";

// cacheComponents and partialPrefetching are documented Next.js 15+ App Router
// features, added by create-next-app during T1.2a scaffolding:
//   cacheComponents: enables the 'use cache' directive for component/page-level
//     caching (docs.nextjs.org/docs/app/api-reference/config/next-config-js/cacheComponents)
//   partialPrefetching: prefetches a reusable App Shell instead of full page
//     variants, reducing prefetch payload size (requires cacheComponents: true).
//     (docs.nextjs.org/docs/app/api-reference/config/next-config-js/partialPrefetching)
// Both are confirmed valid in NextConfig TypeScript types for Next.js 16.4.2.
const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
};

export default nextConfig;
