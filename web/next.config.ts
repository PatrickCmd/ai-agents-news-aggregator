import type { NextConfig } from "next";

const config: NextConfig = {
  // Static export → web/out/ → uploaded to S3 + served via CloudFront.
  // No SSR, no server actions, no middleware. See spec §1.
  output: "export",

  // Trailing slash so /digests/123/ → /digests/123/index.html (CloudFront default object).
  trailingSlash: true,

  // next/image's default optimizer requires a Node server. With static export we ship
  // images verbatim (the small set we have — favicon, logo — doesn't need optimization).
  images: { unoptimized: true },

  experimental: {},
};

export default config;
