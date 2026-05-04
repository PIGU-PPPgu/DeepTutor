"use client";

import type { KGStats, KGNode } from "./graph-api";

interface Props {
  stats: KGStats | null;
  weakNodes: KGNode[];
}

export function GraphStats({ stats, weakNodes }: Props) {
  if (!stats || stats.total === 0) {
    return (
      <div className="text-sm text-[var(--muted-foreground)] p-4">
        暂无统计数据
      </div>
    );
  }

  const total = stats.total;
  const segments = [
    { count: stats.mastered, color: "#22c55e", label: "已掌握" },
    { count: stats.learning, color: "#eab308", label: "学习中" },
    { count: stats.weak, color: "#ef4444", label: "薄弱" },
    { count: stats.unstudied, color: "#94a3b8", label: "未学习" },
  ];

  // SVG donut chart
  const size = 120;
  const cx = size / 2;
  const cy = size / 2;
  const radius = 48;
  const strokeW = 16;
  const circumference = 2 * Math.PI * radius;

  let offset = 0;
  const arcs = segments.map((seg) => {
    const pct = seg.count / total;
    const dash = pct * circumference;
    const gap = circumference - dash;
    const o = offset;
    offset += dash;
    return { ...seg, pct, dash, gap, offset: -circumference / 4 + o };
  });

  const top5Weak = [...weakNodes]
    .filter((n) => n.mastery >= 0 && n.mastery < 0.8)
    .sort((a, b) => a.mastery - b.mastery)
    .slice(0, 5);

  const masteryPct = Math.round(stats.mastery_avg * 100);

  return (
    <div className="space-y-4">
      {/* Donut chart */}
      <div className="flex items-center justify-center">
        <svg width={size} height={size}>
          {arcs.map(
            (a) =>
              a.pct > 0 && (
                <circle
                  key={a.color}
                  cx={cx}
                  cy={cy}
                  r={radius}
                  fill="none"
                  stroke={a.color}
                  strokeWidth={strokeW}
                  strokeDasharray={`${a.dash} ${a.gap}`}
                  strokeDashoffset={a.offset}
                />
              ),
          )}
          <text x={cx} y={cy} textAnchor="middle" dy="-4" fill="var(--foreground)" fontSize="20" fontWeight="bold">
            {masteryPct}%
          </text>
          <text x={cx} y={cy + 14} textAnchor="middle" fill="var(--muted-foreground)" fontSize="10">
            平均掌握
          </text>
        </svg>
      </div>

      {/* Mastery distribution bar chart */}
      <div>
        <div className="text-xs font-medium text-[var(--foreground)] mb-2">掌握分布</div>
        <div className="space-y-1.5">
          {segments.map((s) => {
            const pct = total > 0 ? (s.count / total) * 100 : 0;
            return (
              <div key={s.color} className="flex items-center gap-2 text-xs">
                <span className="w-12 text-right text-[var(--muted-foreground)] shrink-0">{s.label}</span>
                <div className="flex-1 h-3 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${pct}%`, background: s.color, opacity: 0.85 }}
                  />
                </div>
                <span className="w-7 text-[var(--muted-foreground)] shrink-0">{s.count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Progress indicator */}
      <div className="flex items-center gap-2 text-xs bg-[var(--secondary)] rounded px-2.5 py-2">
        <div className="flex-1">
          <div className="flex justify-between mb-1 text-[var(--muted-foreground)]">
            <span>总体进度</span>
            <span className="font-medium" style={{ color: masteryPct >= 80 ? "#22c55e" : masteryPct >= 40 ? "#eab308" : "#ef4444" }}>
              {masteryPct}%
            </span>
          </div>
          <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{
                width: `${masteryPct}%`,
                background: masteryPct >= 80 ? "#22c55e" : masteryPct >= 40 ? "#eab308" : "#ef4444",
              }}
            />
          </div>
        </div>
      </div>

      {/* Top 5 weakest nodes */}
      {top5Weak.length > 0 && (
        <div>
          <div className="text-xs font-medium text-[var(--foreground)] mb-1.5 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />
            最薄弱知识点 Top 5
          </div>
          <div className="space-y-1">
            {top5Weak.map((n, i) => {
              const pct = Math.round(n.mastery * 100);
              const barColor = n.mastery > 0 ? "#ef4444" : "#94a3b8";
              return (
                <div
                  key={n.id}
                  className="text-xs bg-[var(--secondary)] rounded px-2 py-1.5 space-y-1"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="text-[var(--muted-foreground)] shrink-0">#{i + 1}</span>
                      <span className="text-[var(--foreground)] truncate">{n.label}</span>
                    </div>
                    <span className="shrink-0 font-medium" style={{ color: barColor }}>
                      {pct}%
                    </span>
                  </div>
                  <div className="h-1 bg-white/10 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${Math.max(pct, 2)}%`, background: barColor, opacity: 0.8 }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
