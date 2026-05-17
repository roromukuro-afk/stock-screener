export default function ClassificationBadge({ cls }: { cls: string }) {
  const map: Record<string, string> = {
    "採用候補": "badge-adopted",
    "条件付き候補": "badge-conditional",
    "監視候補": "badge-watch",
    "低スコア": "badge-low",
    "除外対象": "badge-excluded",
  };
  return <span className={map[cls] || "badge-low"}>{cls}</span>;
}
