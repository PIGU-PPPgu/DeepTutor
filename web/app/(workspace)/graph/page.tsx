"use client";

import { useState, useEffect, useCallback } from "react";
import { InteractiveGraph } from "@/components/knowledge-graph/InteractiveGraph";
import { GraphStats } from "@/components/knowledge-graph/GraphStats";
import {
  fetchGraph,
  listGraphs,
  generateGraph,
  getWeakNodes,
  fetchStats,
  type KGGraph,
  type KGNode,
  type KGStats,
} from "@/components/knowledge-graph/graph-api";

export default function GraphPage() {
  const [graphs, setGraphs] = useState<string[]>([]);
  const [selectedKb, setSelectedKb] = useState("");
  const [graph, setGraph] = useState<KGGraph | null>(null);
  const [stats, setStats] = useState<KGStats | null>(null);
  const [weakNodes, setWeakNodes] = useState<KGNode[]>([]);
  const [selectedNode, setSelectedNode] = useState<KGNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    listGraphs().then((r) => setGraphs(r.graphs)).catch(() => {});
  }, []);

  const loadGraph = useCallback(async (kbName: string) => {
    if (!kbName) return;
    setLoading(true);
    setError("");
    try {
      const [g, s, w] = await Promise.all([
        fetchGraph(kbName),
        fetchStats(kbName).catch(() => null),
        getWeakNodes(kbName).then((r) => r.nodes).catch(() => []),
      ]);
      setGraph(g);
      setStats(s);
      setWeakNodes(w);
      setSelectedNode(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleGenerate = async () => {
    if (!selectedKb) return;
    // For now, prompt user for content. In future, pull from knowledge base content.
    const content = prompt("粘贴教学内容以生成知识图谱：");
    if (!content) return;
    setLoading(true);
    try {
      const g = await generateGraph(selectedKb, content);
      setGraph(g);
      const [s, w] = await Promise.all([
        fetchStats(selectedKb).catch(() => null),
        getWeakNodes(selectedKb).then((r) => r.nodes).catch(() => []),
      ]);
      setStats(s);
      setWeakNodes(w);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full">
      {/* Main graph area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <div className="flex items-center gap-3 px-4 py-2 border-b border-[var(--border)] bg-[var(--card)]">
          <select
            value={selectedKb}
            onChange={(e) => {
              setSelectedKb(e.target.value);
              loadGraph(e.target.value);
            }}
            className="bg-[var(--secondary)] text-[var(--foreground)] rounded px-2 py-1.5 text-sm border border-[var(--border)]"
          >
            <option value="">选择知识库</option>
            {graphs.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>

          <button
            onClick={handleGenerate}
            disabled={!selectedKb || loading}
            className="px-3 py-1.5 text-sm rounded bg-[var(--primary)] text-[var(--primary-foreground)] disabled:opacity-50"
          >
            {loading ? "生成中..." : "生成图谱"}
          </button>

          {selectedKb && (
            <button
              onClick={() => loadGraph(selectedKb)}
              className="px-3 py-1.5 text-sm rounded border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            >
              刷新
            </button>
          )}
        </div>

        {error && (
          <div className="px-4 py-2 text-sm text-red-400 bg-red-500/10">{error}</div>
        )}

        {/* Graph */}
        <div className="flex-1 relative">
          {graph ? (
            <InteractiveGraph
              graph={graph}
              kbName={selectedKb}
              onNodeClick={setSelectedNode}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-[var(--muted-foreground)]">
              <div className="text-center space-y-2">
                <div className="text-4xl">🕸️</div>
                <div>选择知识库并生成图谱，或导入教材后自动生成</div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Side panel */}
      <div className="w-[280px] shrink-0 border-l border-[var(--border)] bg-[var(--card)] overflow-y-auto p-4">
        {/* Node detail */}
        {selectedNode && (
          <div className="mb-4 pb-4 border-b border-[var(--border)]">
            <div className="text-sm font-medium text-[var(--foreground)] mb-1">{selectedNode.label}</div>
            <div className="text-xs text-[var(--muted-foreground)] mb-2">
              {selectedNode.description || "无描述"}
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span
                className="w-3 h-3 rounded-full"
                style={{
                  background:
                    selectedNode.mastery >= 0.8
                      ? "#22c55e"
                      : selectedNode.mastery >= 0.3
                        ? "#eab308"
                        : selectedNode.mastery > 0
                          ? "#ef4444"
                          : "#94a3b8",
                }}
              />
              <span className="text-[var(--muted-foreground)]">
                掌握度: {(selectedNode.mastery * 100).toFixed(0)}%
              </span>
            </div>
            <div className="text-xs text-[var(--muted-foreground)] mt-1">
              层级: {["学科", "章节", "知识点", "考点"][selectedNode.level] || selectedNode.level}
            </div>
          </div>
        )}

        <GraphStats stats={stats} weakNodes={weakNodes} />
      </div>
    </div>
  );
}
