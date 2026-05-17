import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  basePath: process.env.NEXT_PUBLIC_BASE_PATH ?? "/screener",
  // 本番では NEXT_PUBLIC_BASE_PATH を上書きできる
  // ルートのリダイレクトはVercel等のホスト側ルーティングに任せる
  reactStrictMode: true,
};

export default nextConfig;
