"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import { ChevronRight, ChevronLeft } from "lucide-react";
import { fetchGraph, fetchStats, type KGGraph, type KGStats, type KGNode } from "@/components/knowledge-graph/graph-api";

function nodeColor(mastery: number): string {
  if (mastery >= 0.8) return "#22c55e";
  if (mastery >= 0.3) return "#eab308";
  if (mastery > 0) return "#ef4444";
  return "#94a3b8";
}

interface Props {
  kbName: string | null;
  onNodeClick?: (nodeId: string, label: string) => void;
}

export function KnowledgeGraphPanel({ kbName, onNodeClick }: Props) {
  const [open, setOpen] = useState(false);
  const [stats, setStats] = useState<KGStats | null>(null);
  const [weakNodes, setWeakNodes] = useState<KGNode[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !kbName) return;
    setLoading(true);
    Promise.all([fetchStats(kbName).catch(() => null)])
      .then(([s]) => {
        setStats(s);
        if (s) {
          fetchGraph(kbName).then((g: KGGraph) => {
            const weak = g.nodes
              .filter((n) => n.mastery > 0 && n.mastery < 0.3)
              .sort((a, b) => a.mastery - b.mastery)
              .slice(0, 8);
            setWeakNodes(weak);
          }).catch(() => {});
        }
      })
      .finally(() => setLoading(false));
  }, [open, kbName]);

  if (!kbName) {
    return (
      <button
        className="fixed right-0 top-1/2 -translate-y-1/2 z-20 bg-[var(--card)] border border-r-0 border-[var(--border)] rounded-l-lg p-2 text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors opacity-40 cursor-not-allowed"
        disabled
        title="Select a knowledge base to view graph"
      >
        <ChevronLeft size={16} />
      </button>
    );
  }

  return (
    <>
      {/* Toggle button - always visible */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed right-0 top-1/2 -translate-y-1/2 z-20 bg-[var(--card)] border border-r-0 border-[var(--border)] rounded-l-lg p-2 text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors shadow-sm"
          title="知识图谱"
        >
          <ChevronLeft size={16} />
        </button>
      )}

      {/* Panel */}
      <div
        className={`${
          open ? "translate-x-0" : "translate-x-full"
        } fixed right-0 top-0 h-full w-[300px] z-30 bg-[var(--card)] border-l border-[var(--border)] shadow-xl transition-transform duration-200 ease-in-out overflow-y-auto`}
      >
        {/* Header */}
        <div className="sticky top-0 bg-[var(--card)] border-b border-[var(--border)] px-4 py-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[var(--foreground)]">知识图谱</h3>
          <button
            onClick={() => setOpen(false)}
            className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
          >
            <ChevronRight size={16} />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12 text-[var(--muted-foreground)] text-sm">
            加载中...
          </div>
        ) : stats ? (
          <div className="p-4 space-y-5">
            {/* Donut chart */}
            <DonutChart stats={stats} />

            {/* Overall progress */}
            <div>
              <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)] mb-1">
                <span>总体掌握度</span>
                <span>{(stats.mastery_avg * 100).toFixed(0)}%</span>
              </div>
              <div className="h-2 bg-[var(--secondary)] rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${stats.mastery_avg * 100}%`,
                    background: `linear-gradient(90deg, #22c55e ${stats.mastered / stats.total * 100}%, #eab308 60%, #ef4444)`,
                  }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-[var(--muted-foreground)] mt-1">
                <span>已掌握 {stats.mastered}</span>
                <span>学习中 {stats.learning}</span>
                <span>薄弱 {stats.weak}</span>
                <span>未学习 {stats.unstudied}</span>
              </div>
            </div>

            {/* Weak nodes */}
            {weakNodes.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-[var(--foreground)] mb-2">⚠️ 薄弱知识点</h4>
                <div className="space-y-1.5">
                  {weakNodes.map((node) => (
                    <button
                      key={node.id}
                      onClick={() => onNodeClick?.(node.id, node.label)}
                      className="w-full text-left px-3 py-2 rounded-lg bg-[var(--secondary)]/50 hover:bg-[var(--secondary)] transition-colors"
                    >
                      <div className="text-xs text-[var(--foreground)]">{node.label}</div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <div className="flex-1 h-1 bg-[var(--background)] rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{ width: `${node.mastery * 100}%`, background: nodeColor(node.mastery) }}
                          />
                        </div>
                        <span className="text-[10px] text-[var(--muted-foreground)]">
                          {(node.mastery * 100).toFixed(0)}%
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="py-12 text-center text-sm text-[var(--muted-foreground)]">
            无法加载图谱数据
          </div>
        )}
      </div>

      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-20 bg-black/20 md:hidden"
          onClick={() => setOpen(false)}
        />
      )}
    </>
  );
}

/** Simple SVG donut chart showing mastery breakdown */
function DonutChart({ stats }: { stats: KGStats }) {
  const size = 120;
  const thickness = 16;
  const radius = (size - thickness) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * radius;

  const segments = [
    { value: stats.mastered, color: "#22c55e", label: "已掌握" },
    { value: stats.learning, color: "#eab308", label: "学习中" },
    { value: stats.weak, color: "#ef4444", label: "薄弱" },
    { value: stats.unstudied, color: "#94a3b8", label: "未学习" },
  ];

  let offset = 0;
  const arcs = segments.map((s) => {
    const len = stats.total > 0 ? (s.value / stats.total) * circumference : 0;
    const arc = { ...s, dashArray: `${len} ${circumference - len}`, dashOffset: -offset, len };
    offset += len;
    return arc;
  });

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} className="-rotate-90">
        {arcs.map((a) =>
          a.len > 0 ? (
            <circle
              key={a.label}
              cx={cx}
              cy={cy}
              r={radius}
              fill="none"
              stroke={a.color}
              strokeWidth={thickness}
              strokeDasharray={a.dashArray}
              strokeDashoffset={a.dashOffset}
              className="transition-all duration-500"
            />
          ) : null
        )}
      </svg>
      <div className="text-center mt-2">
        <div className="text-lg font-bold text-[var(--foreground)]">{stats.total}</div>
        <div className="text-[10px] text-[var(--muted-foreground)]">知识点总数</div>
      </div>
    </div>
  );
}
