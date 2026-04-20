"use client";

import { useMemo, useState, useEffect, useCallback } from "react";
import { InteractiveGraph } from "@/components/knowledge-graph/InteractiveGraph";
import { GraphStats } from "@/components/knowledge-graph/GraphStats";
import { GraphTree } from "@/components/knowledge-graph/GraphTree";
import {
  fetchGraph,
  listGraphs,
  generateGraph,
  getWeakNodes,
  fetchStats,
  expandGraph,
  type KGGraph,
  type KGNode,
  type KGStats,
} from "@/components/knowledge-graph/graph-api";

function masteryBadge(mastery: number) {
  if (mastery >= 0.8) return { label: "已掌握", color: "#22c55e" };
  if (mastery >= 0.3) return { label: "学习中", color: "#eab308" };
  if (mastery > 0) return { label: "薄弱", color: "#ef4444" };
  return { label: "未学习", color: "#94a3b8" };
}

function filterGraph(graph: KGGraph | null, search: string, masteryFilter: string): KGGraph | null {
  if (!graph) return null;

  const query = search.trim().toLowerCase();
  const nodes = graph.nodes.filter((node) => {
    const matchSearch = !query
      || node.label.toLowerCase().includes(query)
      || node.description?.toLowerCase().includes(query)
      || String(node.source || "").toLowerCase().includes(query);

    const matchMastery = masteryFilter === "all"
      || (masteryFilter === "weak" && node.mastery > 0 && node.mastery < 0.3)
      || (masteryFilter === "learning" && node.mastery >= 0.3 && node.mastery < 0.8)
      || (masteryFilter === "mastered" && node.mastery >= 0.8)
      || (masteryFilter === "unstudied" && node.mastery <= 0);

    return matchSearch && matchMastery;
  });

  const nodeIds = new Set(nodes.map((n) => n.id));
  const edges = graph.edges.filter((e) => nodeIds.has(e.source_id) && nodeIds.has(e.target_id));
  return { nodes, edges };
}

/** Build ancestor path for a node, from root to the node itself */
function buildBreadcrumb(nodes: KGNode[], nodeId: string): KGNode[] {
  const map = new Map(nodes.map((n) => [n.id, n]));
  const path: KGNode[] = [];
  let current: KGNode | undefined = map.get(nodeId);
  while (current) {
    path.unshift(current);
    current = current.parent_id ? map.get(current.parent_id) : undefined;
  }
  return path;
}

export default function GraphPage() {
  const [graphs, setGraphs] = useState<string[]>([]);
  const [selectedKb, setSelectedKb] = useState("");
  const [graph, setGraph] = useState<KGGraph | null>(null);
  const [stats, setStats] = useState<KGStats | null>(null);
  const [weakNodes, setWeakNodes] = useState<KGNode[]>([]);
  const [selectedNode, setSelectedNode] = useState<KGNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [treeSearch, setTreeSearch] = useState("");
  const [highlightNodeId, setHighlightNodeId] = useState<string | null>(null);
  const [masteryFilter, setMasteryFilter] = useState<"all" | "weak" | "learning" | "mastered" | "unstudied">("all");

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
      setHighlightNodeId(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-select KB from ?kb= URL param once graphs list is loaded
  useEffect(() => {
    if (graphs.length === 0) return;
    const params = new URLSearchParams(window.location.search);
    const kbParam = params.get("kb");
    if (kbParam && graphs.includes(kbParam) && !selectedKb) {
      setSelectedKb(kbParam);
      void loadGraph(kbParam);
    }
    // Only fire once when graphs first load
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphs]);

  const [expandStatus, setExpandStatus] = useState("");

  const handleExpand = async () => {
    if (!selectedKb) return;
    setExpandStatus("正在拆解...");
    setLoading(true);
    try {
      const r = await expandGraph(selectedKb, 5, 1500);
      setGraph(r.graph);
      const [s, w] = await Promise.all([
        fetchStats(selectedKb).catch(() => null),
        getWeakNodes(selectedKb).then((r) => r.nodes).catch(() => []),
      ]);
      setStats(s);
      setWeakNodes(w);
      setExpandStatus(`拆解完成：${r.nodes} 节点，${r.edges} 边`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "拆解失败");
      setExpandStatus("");
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    if (!selectedKb) return;
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
      setSelectedNode(null);
      setHighlightNodeId(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setLoading(false);
    }
  };

  const visibleGraph = useMemo(() => filterGraph(graph, treeSearch, masteryFilter), [graph, treeSearch, masteryFilter]);
  const selectedBadge = selectedNode ? masteryBadge(selectedNode.mastery) : null;
  const metadataEntries = selectedNode ? Object.entries(selectedNode.metadata || {}).slice(0, 8) : [];

  // Breadcrumb path for selected node
  const breadcrumb = useMemo(() => {
    if (!selectedNode || !graph) return [];
    return buildBreadcrumb(graph.nodes, selectedNode.id);
  }, [selectedNode, graph]);

  // Mastery-adaptive action data for the node detail panel
  const nodeActionData = useMemo(() => {
    if (!selectedNode) return null;
    const topicEnc = encodeURIComponent(selectedNode.label);
    const kbSuffix = selectedKb ? `&kb=${encodeURIComponent(selectedKb)}` : "";
    const retSuffix = selectedKb
      ? `&from=graph&kb=${encodeURIComponent(selectedKb)}`
      : "&from=graph";
    const m = selectedNode.mastery;

    const hint =
      m === 0 ? "建议先系统学习" :
      m < 0.3 ? "掌握度低，先学后练" :
      m < 0.8 ? "做题巩固理解" :
      "已掌握，深化拓展";

    const actions = [
      { key: "guide", label: "学习引导", href: `/guide?topic=${topicEnc}${retSuffix}` },
      { key: "quiz",  label: "生成测题", href: `/chat?capability=deep_question&topic=${topicEnc}${kbSuffix}${retSuffix}` },
      { key: "chat",  label: "深度问答", href: `/chat?topic=${encodeURIComponent(`请解释并帮助我理解：${selectedNode.label}`)}${kbSuffix}${retSuffix}` },
    ];

    // First in list = primary (recommended)
    let order: string[];
    if (m === 0)       order = ["guide", "chat", "quiz"];
    else if (m < 0.3)  order = ["guide", "quiz", "chat"];
    else if (m < 0.8)  order = ["quiz", "guide", "chat"];
    else               order = ["chat", "quiz", "guide"];

    const orderedActions = order.map((k) => actions.find((a) => a.key === k)!);
    return { hint, orderedActions };
  }, [selectedNode, selectedKb]);

  return (
    <div className="flex h-full">
      {graph && (
        <GraphTree
          nodes={graph.nodes}
          edges={graph.edges}
          selectedNodeId={highlightNodeId}
          onSelect={(id) => {
            setHighlightNodeId(id);
            const node = graph.nodes.find((n) => n.id === id);
            if (node) setSelectedNode(node);
          }}
          searchQuery={treeSearch}
          onSearchChange={setTreeSearch}
        />
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex flex-wrap items-center gap-3 px-4 py-2 border-b border-[var(--border)] bg-[var(--card)]">
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
              onClick={handleExpand}
              disabled={!selectedKb || loading}
              className="px-3 py-1.5 text-sm rounded bg-orange-600 text-white disabled:opacity-50"
            >
              {expandStatus || "深度拆解"}
            </button>
          )}

          {selectedKb && (
            <button
              onClick={() => loadGraph(selectedKb)}
              className="px-3 py-1.5 text-sm rounded border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            >
              刷新
            </button>
          )}

          <select
            value={masteryFilter}
            onChange={(e) => setMasteryFilter(e.target.value as typeof masteryFilter)}
            className="bg-[var(--secondary)] text-[var(--foreground)] rounded px-2 py-1.5 text-sm border border-[var(--border)]"
          >
            <option value="all">全部掌握度</option>
            <option value="weak">只看薄弱</option>
            <option value="learning">只看学习中</option>
            <option value="mastered">只看已掌握</option>
            <option value="unstudied">只看未学习</option>
          </select>

          {weakNodes.length > 0 && (
            <button
              onClick={() => {
                const weakest = [...weakNodes].sort((a, b) => a.mastery - b.mastery)[0];
                setHighlightNodeId(weakest.id);
                setSelectedNode(weakest);
                setTreeSearch(weakest.label);
              }}
              className="px-3 py-1.5 text-sm rounded border border-red-500/40 text-red-300 hover:bg-red-500/10"
            >
              定位最薄弱节点
            </button>
          )}

          {(treeSearch || masteryFilter !== "all") && (
            <button
              onClick={() => {
                setTreeSearch("");
                setMasteryFilter("all");
              }}
              className="px-3 py-1.5 text-sm rounded border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            >
              清空筛选
            </button>
          )}

          {visibleGraph && (
            <div className="ml-auto text-xs text-[var(--muted-foreground)]">
              当前显示 {visibleGraph.nodes.length}/{graph?.nodes.length ?? 0} 节点
            </div>
          )}
        </div>

        {/* Breadcrumb */}
        {breadcrumb.length > 0 && (
          <div className="flex items-center gap-1 px-4 py-1.5 border-b border-[var(--border)] bg-[var(--card)]/50 text-xs overflow-x-auto min-h-[32px]">
            {breadcrumb.map((crumb, i) => (
              <span key={crumb.id} className="flex items-center gap-1 shrink-0">
                {i > 0 && (
                  <svg className="text-[var(--muted-foreground)]" width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
                    <path d="M3 1l5 4-5 4z" />
                  </svg>
                )}
                <button
                  onClick={() => {
                    setHighlightNodeId(crumb.id);
                    setSelectedNode(crumb);
                  }}
                  className={`px-1.5 py-0.5 rounded transition-colors ${
                    crumb.id === selectedNode?.id
                      ? "text-[var(--foreground)] font-medium"
                      : "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-white/5"
                  }`}
                >
                  {crumb.label}
                </button>
              </span>
            ))}
          </div>
        )}

        {error && (
          <div className="px-4 py-2 text-sm text-red-400 bg-red-500/10">{error}</div>
        )}

        <div className="flex-1 relative">
          {visibleGraph ? (
            <InteractiveGraph
              graph={visibleGraph}
              kbName={selectedKb}
              highlightedNodeId={highlightNodeId}
              onNodeClick={(node) => {
                setSelectedNode(node);
                setHighlightNodeId(node.id);
              }}
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

      <div className="w-[320px] shrink-0 border-l border-[var(--border)] bg-[var(--card)] overflow-y-auto p-4">
        {selectedNode && selectedBadge && (
          <div className="mb-4 pb-4 border-b border-[var(--border)] space-y-3">
            <div>
              <div className="text-sm font-medium text-[var(--foreground)] mb-1">{selectedNode.label}</div>
              <div className="text-xs text-[var(--muted-foreground)]">{selectedNode.description || "无描述"}</div>
            </div>

            <div className="flex items-center gap-2 text-xs">
              <span className="w-3 h-3 rounded-full" style={{ background: selectedBadge.color }} />
              <span className="text-[var(--muted-foreground)]">
                {selectedBadge.label} · {(selectedNode.mastery * 100).toFixed(0)}%
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs text-[var(--muted-foreground)]">
              <div>层级：{["学科", "章节", "知识点", "考点"][selectedNode.level] || selectedNode.level}</div>
              <div>来源：{selectedNode.source || "未知"}</div>
            </div>

            {metadataEntries.length > 0 && (
              <div>
                <div className="text-xs font-medium text-[var(--foreground)] mb-2">元数据</div>
                <div className="space-y-1.5">
                  {metadataEntries.map(([key, value]) => (
                    <div key={key} className="text-xs text-[var(--muted-foreground)] break-all">
                      <span className="text-[var(--foreground)]">{key}：</span>
                      {typeof value === "string" ? value : JSON.stringify(value)}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {nodeActionData && (
              <div className="pt-1 space-y-1.5">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="text-xs font-medium text-[var(--foreground)]">开始学习</div>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--muted)] text-[var(--muted-foreground)]">
                    {nodeActionData.hint}
                  </span>
                </div>
                {nodeActionData.orderedActions.map((action, idx) => (
                  <a
                    key={action.key}
                    href={action.href}
                    className={`flex items-center gap-2 w-full px-3 py-2 rounded-md text-xs ${
                      idx === 0
                        ? "bg-[var(--primary)] text-[var(--primary-foreground)] hover:opacity-90 transition-opacity"
                        : "bg-[var(--secondary)] text-[var(--foreground)] border border-[var(--border)] hover:bg-[var(--muted)] transition-colors"
                    }`}
                  >
                    {action.key === "guide" && (
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/>
                      </svg>
                    )}
                    {action.key === "quiz" && (
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                      </svg>
                    )}
                    {action.key === "chat" && (
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                      </svg>
                    )}
                    {action.label}
                    {idx === 0 && (
                      <span className="ml-auto text-[9px] opacity-60">推荐</span>
                    )}
                  </a>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="mb-4 pb-4 border-b border-[var(--border)]">
          <div className="text-xs font-medium text-[var(--foreground)] mb-2">掌握度图例</div>
          <div className="space-y-1 text-xs">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-[#22c55e]" />
              <span className="text-[var(--muted-foreground)]">已掌握 (≥80%)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-[#eab308]" />
              <span className="text-[var(--muted-foreground)]">学习中 (30-80%)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-[#ef4444]" />
              <span className="text-[var(--muted-foreground)]">薄弱 (&lt;30%)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-[#94a3b8]" />
              <span className="text-[var(--muted-foreground)]">未学习</span>
            </div>
          </div>
          <div className="mt-2 text-[10px] text-[var(--muted-foreground)]/60">双击节点可聚焦邻域</div>
        </div>

        <GraphStats stats={stats} weakNodes={weakNodes} />
      </div>
    </div>
  );
}
