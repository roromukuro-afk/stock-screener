const map: Record<string, string> = {
  "先行大商い": "bg-purple-100 text-purple-700",
  "売り枯れ": "bg-blue-100 text-blue-700",
  "価格維持": "bg-cyan-100 text-cyan-700",
  "再点火待ち": "bg-yellow-100 text-yellow-700",
  "再点火開始": "bg-green-100 text-green-700",
  "天井大商い警戒": "bg-red-100 text-red-700",
  "人気離散": "bg-gray-100 text-gray-500",
  "出来高不足": "bg-gray-100 text-gray-400",
  "判定不能": "bg-gray-50 text-gray-400",
};

export default function VolCycleBadge({ state }: { state?: string }) {
  if (!state) return null;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${map[state] || "bg-gray-100 text-gray-500"}`}>
      {state}
    </span>
  );
}
