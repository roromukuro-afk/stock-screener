export default function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score));
  const color = pct >= 85 ? "#16a34a" : pct >= 75 ? "#2563eb" : pct >= 65 ? "#d97706" : "#9ca3af";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-100 rounded-full h-2">
        <div className="h-2 rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-sm font-bold" style={{ color, minWidth: "2.5rem" }}>{pct.toFixed(0)}</span>
    </div>
  );
}
