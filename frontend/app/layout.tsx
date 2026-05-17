import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {
  title: "短期急騰3000円以下AIスクリーナー",
  description: "日本株・米国株・ADR 短期急騰パターン分析ツール（投資助言ではありません）",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="min-h-screen" style={{ background: "#f1f5f9" }}>
        <Navbar />
        <main className="max-w-screen-2xl mx-auto px-4 py-6">{children}</main>
        <footer className="text-center text-xs text-gray-400 py-4 border-t border-gray-200 mt-8 bg-white">
          ⚠️ このサイトは投資助言ではありません。売買推奨ではありません。最終判断はユーザー自身が行ってください。
        </footer>
      </body>
    </html>
  );
}
