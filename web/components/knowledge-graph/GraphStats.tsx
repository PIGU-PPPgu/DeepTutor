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

  return (
    <div className="space-y-4">
      {/* Donut */}
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
            {(stats.mastery_avg * 100).toFixed(0)}%
          </text>
          <text x={cx} y={cy + 14} textAnchor="middle" fill="var(--muted-foreground)" fontSize="10">
            平均掌握
          </text>
        </svg>
      </div>

      {/* Legend */}
      <div className="grid grid-cols-2 gap-1 text-xs">
        {segments.map((s) => (
          <div key={s.color} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ background: s.color }} />
            <span className="text-[var(--muted-foreground)]">
              {s.label} ({s.count})
            </span>
          </div>
        ))}
      </div>

      {/* Weak nodes */}
      {weakNodes.length > 0 && (
        <div>
          <div className="text-sm font-medium text-[var(--foreground)] mb-1.5">薄弱知识点</div>
          <div className="space-y-1">
            {weakNodes.slice(0, 8).map((n) => (
              <div
                key={n.id}
                className="flex items-center justify-between text-xs bg-[var(--secondary)] rounded px-2 py-1.5"
              >
                <span className="text-[var(--foreground)] truncate">{n.label}</span>
                <span className="text-[var(--muted-foreground)] ml-2 shrink-0">
                  {(n.mastery * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
