"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/", label: "ダッシュボード" },
  { href: "/universe", label: "ユニバース管理" },
  { href: "/screening", label: "全銘柄スクリーニング" },
  { href: "/ranking", label: "候補ランキング" },
  { href: "/excluded", label: "除外銘柄" },
  { href: "/exclusion-list", label: "除外リスト管理" },
  { href: "/aar", label: "AAR出力" },
  { href: "/backtest", label: "バックテスト" },
  { href: "/settings", label: "設定" },
  { href: "/deploy-status", label: "公開ステータス" },
];

export default function Navbar() {
  const path = usePathname();
  // basePath が "/screener" の場合、usePathname はそれを除いた値を返す
  const norm = path || "/";
  return (
    <nav style={{ background: "#0f172a" }} className="text-white shadow-lg">
      <div className="max-w-screen-2xl mx-auto px-4 flex items-center gap-1 overflow-x-auto">
        <Link href="/" className="flex-shrink-0 font-bold text-sm py-4 pr-4 text-blue-300 whitespace-nowrap">
          📈 短期急騰AIスクリーナー
        </Link>
        {navItems.map((item) => {
          const active =
            item.href === "/"
              ? norm === "/" || norm === ""
              : norm.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex-shrink-0 px-3 py-4 text-sm whitespace-nowrap transition-colors ${
                active
                  ? "text-blue-300 border-b-2 border-blue-300"
                  : "text-gray-300 hover:text-white"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
