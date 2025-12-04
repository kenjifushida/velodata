import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'p1-d9ebd2ee.imageflux.jp',
      },
      {
        protocol: 'https',
        hostname: '*.imageflux.jp',
      },
      {
        protocol: 'https',
        hostname: 'netmall.hardoff.co.jp',
      },
    ],
  },
};

export default nextConfig;
