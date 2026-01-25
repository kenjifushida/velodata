import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      // Hard-Off
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
      // Yahoo Auctions Japan
      {
        protocol: 'https',
        hostname: 'auc-pctr.c.yimg.jp',
      },
      {
        protocol: 'https',
        hostname: '*.c.yimg.jp',
      },
      // Mercari Japan
      {
        protocol: 'https',
        hostname: 'static.mercdn.net',
      },
      {
        protocol: 'https',
        hostname: '*.mercdn.net',
      },
      // PayPay Flea Market
      {
        protocol: 'https',
        hostname: 'paypayfleamarket.yahoo.co.jp',
      },
      {
        protocol: 'https',
        hostname: '*.paypay.ne.jp',
      },
      // SNKRDUNK
      {
        protocol: 'https',
        hostname: '*.snkrdunk.com',
      },
      // Yuyutei
      {
        protocol: 'https',
        hostname: '*.yuyutei.jp',
      },
      {
        protocol: 'https',
        hostname: 'yuyutei.jp',
      },
    ],
  },
};

export default nextConfig;
