"use client";

import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import type { KGNode, KGEdge } from "./graph-api";

interface TreeNode {
  node: KGNode;
  children: TreeNode[];
}

interface Props {
  nodes: KGNode[];
  edges: KGEdge[];
  selectedNodeId: string | null;
  onSelect: (nodeId: string) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
}

function masteryColor(mastery: number): string {
  if (mastery >= 0.8) return "#22c55e";
  if (mastery >= 0.3) return "#eab308";
  if (mastery > 0) return "#ef4444";
  return "#94a3b8";
}

function buildTree(nodes: KGNode[]): TreeNode[] {
  const map = new Map<string, TreeNode>();
  const roots: TreeNode[] = [];

  for (const n of nodes) {
    map.set(n.id, { node: n, children: [] });
  }

  for (const n of nodes) {
    const tn = map.get(n.id)!;
    if (n.parent_id && map.has(n.parent_id)) {
      map.get(n.parent_id)!.children.push(tn);
    } else {
      roots.push(tn);
    }
  }

  const sortChildren = (t: TreeNode) => {
    t.children.sort((a, b) => a.node.label.localeCompare(b.node.label, "zh"));
    t.children.forEach(sortChildren);
  };
  roots.sort((a, b) => a.node.label.localeCompare(b.node.label, "zh"));
  roots.forEach(sortChildren);

  return roots;
}

function countDescendants(tn: TreeNode): number {
  let count = tn.children.length;
  for (const c of tn.children) count += countDescendants(c);
  return count;
}

function getAncestorIds(nodes: KGNode[], matchedIds: Set<string>): Set<string> {
  const parentMap = new Map<string, string | null>();
  for (const n of nodes) parentMap.set(n.id, n.parent_id ?? null);

  const ancestors = new Set<string>();
  for (const id of matchedIds) {
    let current = parentMap.get(id);
    while (current) {
      ancestors.add(current);
      current = parentMap.get(current) ?? null;
    }
  }
  return ancestors;
}

function matchNodes(nodes: KGNode[], query: string): Set<string> {
  if (!query.trim()) return new Set(nodes.map((n) => n.id));
  const q = query.toLowerCase();
  const matched = new Set<string>();
  for (const n of nodes) {
    if (n.label.toLowerCase().includes(q) || n.description?.toLowerCase().includes(q)) {
      matched.add(n.id);
    }
  }
  const ancestors = getAncestorIds(nodes, matched);
  for (const a of ancestors) matched.add(a);
  return matched;
}

/** Flatten tree into ordered visible node IDs (for keyboard navigation) */
function flattenVisible(
  treeNodes: TreeNode[],
  visibleIds: Set<string>,
  expandedIds: Set<string>,
  result: string[] = []
): string[] {
  for (const tn of treeNodes) {
    if (!visibleIds.has(tn.node.id)) continue;
    result.push(tn.node.id);
    if (expandedIds.has(tn.node.id) && tn.children.length > 0) {
      flattenVisible(tn.children, visibleIds, expandedIds, result);
    }
  }
  return result;
}

function TreeRow({
  treeNode,
  depth,
  selectedNodeId,
  focusedId,
  onSelect,
  expandedIds,
  toggleExpand,
  visibleIds,
  searchQuery,
}: {
  treeNode: TreeNode;
  depth: number;
  selectedNodeId: string | null;
  focusedId: string | null;
  onSelect: (nodeId: string) => void;
  expandedIds: Set<string>;
  toggleExpand: (id: string) => void;
  visibleIds: Set<string>;
  searchQuery: string;
}) {
  const { node, children } = treeNode;
  const isSelected = selectedNodeId === node.id;
  const isFocused = focusedId === node.id;
  const hasChildren = children.length > 0;
  const isExpanded = expandedIds.has(node.id);

  if (!visibleIds.has(node.id)) return null;

  const visibleChildren = children.filter((c) => visibleIds.has(c.node.id));
  const showChildren = hasChildren && isExpanded && visibleChildren.length > 0;
  const query = searchQuery.trim().toLowerCase();
  const isMatch = !!query && (
    node.label.toLowerCase().includes(query)
    || node.description?.toLowerCase().includes(query)
  );

  return (
    <>
      <div
        data-node-id={node.id}
        className={`group flex items-center gap-1.5 px-2 py-1 cursor-pointer transition-colors ${
          isSelected ? "bg-blue-500/15" : isFocused ? "bg-white/8" : "hover:bg-white/5"
        } ${isFocused ? "outline outline-1 outline-blue-500/40 outline-offset-[-1px]" : ""}`}
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
        onClick={() => onSelect(node.id)}
        tabIndex={-1}
      >
        {/* Selected indicator */}
        <div
          className={`w-0.5 h-4 rounded-full shrink-0 ${
            isSelected ? "bg-blue-500" : "bg-transparent"
          }`}
        />

        {/* Expand/collapse */}
        {hasChildren ? (
          <button
            className="w-4 h-4 flex items-center justify-center text-[var(--muted-foreground)] hover:text-white shrink-0 transition-transform"
            onClick={(e) => {
              e.stopPropagation();
              toggleExpand(node.id);
            }}
            style={{ transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)" }}
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
              <path d="M3 1l5 4-5 4z" />
            </svg>
          </button>
        ) : (
          <div className="w-4 shrink-0" />
        )}

        {/* Mastery dot */}
        <span
          className="w-2.5 h-2.5 rounded-full shrink-0"
          style={{ background: masteryColor(node.mastery) }}
        />

        {/* Label */}
        <span className={`text-sm truncate flex-1 ${isMatch ? "text-amber-300 font-medium" : "text-white"}`}>
          {node.label}
        </span>

        {/* Descendant count badge */}
        {hasChildren && (
          <span className="text-[10px] bg-white/10 text-[var(--muted-foreground)] rounded px-1 shrink-0">
            {countDescendants(treeNode)}
          </span>
        )}
      </div>

      {/* Children with animation */}
      <div
        className="overflow-hidden transition-all duration-200"
        style={{
          maxHeight: showChildren ? `${visibleChildren.length * 200}px` : "0px",
          opacity: showChildren ? 1 : 0,
        }}
      >
        {showChildren &&
          visibleChildren.map((child) => (
            <TreeRow
              key={child.node.id}
              treeNode={child}
              depth={depth + 1}
              selectedNodeId={selectedNodeId}
              focusedId={focusedId}
              onSelect={onSelect}
              expandedIds={expandedIds}
              toggleExpand={toggleExpand}
              visibleIds={visibleIds}
              searchQuery={searchQuery}
            />
          ))}
      </div>
    </>
  );
}

export function GraphTree({
  nodes,
  edges: _edges,
  selectedNodeId,
  onSelect,
  searchQuery,
  onSearchChange,
}: Props) {
  const tree = useMemo(() => buildTree(nodes), [nodes]);
  const visibleIds = useMemo(() => matchNodes(nodes, searchQuery), [nodes, searchQuery]);

  const autoExpandedIds = useMemo(() => {
    if (!searchQuery.trim()) return new Set<string>();
    const expanded = new Set<string>();
    const expandParents = (treeNodes: TreeNode[]) => {
      for (const tn of treeNodes) {
        if (tn.children.some((c) => visibleIds.has(c.node.id))) {
          expanded.add(tn.node.id);
        }
        expandParents(tn.children);
      }
    };
    expandParents(tree);
    return expanded;
  }, [searchQuery, tree, visibleIds]);

  const [manualExpanded, setManualExpanded] = useState<Set<string>>(() => {
    const rootish = new Set<string>();
    for (const n of nodes) {
      if (!n.parent_id || n.level <= 1) rootish.add(n.id);
    }
    return rootish;
  });

  const expandedIds = useMemo(() => {
    if (searchQuery.trim()) return autoExpandedIds;
    return manualExpanded;
  }, [searchQuery, autoExpandedIds, manualExpanded]);

  const toggleExpand = useCallback((id: string) => {
    setManualExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  // Keyboard navigation
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const treeListRef = useRef<HTMLDivElement>(null);

  const flatIds = useMemo(
    () => flattenVisible(tree, visibleIds, expandedIds),
    [tree, visibleIds, expandedIds]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (flatIds.length === 0) return;
      const currentIdx = focusedId ? flatIds.indexOf(focusedId) : -1;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        const next = flatIds[Math.min(currentIdx + 1, flatIds.length - 1)];
        setFocusedId(next);
        treeListRef.current?.querySelector(`[data-node-id="${next}"]`)?.scrollIntoView({ block: "nearest" });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const prev = flatIds[Math.max(currentIdx - 1, 0)];
        setFocusedId(prev);
        treeListRef.current?.querySelector(`[data-node-id="${prev}"]`)?.scrollIntoView({ block: "nearest" });
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        if (focusedId) toggleExpand(focusedId);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        if (focusedId) toggleExpand(focusedId);
      } else if (e.key === "Enter" && focusedId) {
        e.preventDefault();
        onSelect(focusedId);
      }
    },
    [flatIds, focusedId, toggleExpand, onSelect]
  );

  // Scroll selected node into view when it changes
  useEffect(() => {
    if (selectedNodeId) {
      setFocusedId(selectedNodeId);
      setTimeout(() => {
        treeListRef.current
          ?.querySelector(`[data-node-id="${selectedNodeId}"]`)
          ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }, 50);
    }
  }, [selectedNodeId]);

  // Drag-to-resize sidebar
  const [sidebarWidth, setSidebarWidth] = useState(280);
  const dragState = useRef({ dragging: false, startX: 0, startWidth: 280 });

  const onResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragState.current = { dragging: true, startX: e.clientX, startWidth: sidebarWidth };

    const onMove = (ev: MouseEvent) => {
      if (!dragState.current.dragging) return;
      const delta = ev.clientX - dragState.current.startX;
      setSidebarWidth(Math.max(180, Math.min(480, dragState.current.startWidth + delta)));
    };
    const onUp = () => {
      dragState.current.dragging = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [sidebarWidth]);

  const matchCount = useMemo(() => {
    if (!searchQuery.trim()) return 0;
    const q = searchQuery.toLowerCase();
    return nodes.filter(
      (n) => n.label.toLowerCase().includes(q) || n.description?.toLowerCase().includes(q)
    ).length;
  }, [nodes, searchQuery]);

  return (
    <div
      className="shrink-0 bg-[var(--card)] border-r border-[var(--border)] flex flex-col h-full relative"
      style={{ width: sidebarWidth }}
      onKeyDown={handleKeyDown}
      tabIndex={0}
      aria-label="知识点树"
    >
      {/* Search */}
      <div className="p-3 border-b border-[var(--border)]">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="搜索知识点... (↑↓ 导航)"
          className="w-full px-3 py-1.5 text-sm rounded bg-[var(--secondary)] text-[var(--foreground)] border border-[var(--border)] placeholder:text-[var(--muted-foreground)] outline-none focus:border-blue-500"
        />
      </div>

      {/* Tree */}
      <div ref={treeListRef} className="flex-1 overflow-y-auto py-1">
        {tree.length === 0 ? (
          <div className="text-center text-sm text-[var(--muted-foreground)] py-8">
            暂无数据
          </div>
        ) : (
          tree.map((tn) => (
            <TreeRow
              key={tn.node.id}
              treeNode={tn}
              depth={0}
              selectedNodeId={selectedNodeId}
              focusedId={focusedId}
              onSelect={(id) => {
                setFocusedId(id);
                onSelect(id);
              }}
              expandedIds={expandedIds}
              toggleExpand={toggleExpand}
              visibleIds={visibleIds}
              searchQuery={searchQuery}
            />
          ))
        )}
      </div>

      {/* Footer */}
      <div className="px-3 py-2 border-t border-[var(--border)] text-xs text-[var(--muted-foreground)] flex items-center justify-between gap-2">
        <span>共 {nodes.length} 个节点</span>
        {!!searchQuery.trim() && <span className="text-amber-400">命中 {matchCount} 个</span>}
      </div>

      {/* Resize handle */}
      <div
        onMouseDown={onResizeStart}
        className="absolute top-0 right-0 w-1.5 h-full cursor-col-resize hover:bg-blue-500/30 transition-colors group"
        title="拖动调整宽度"
      >
        <div className="absolute right-0 top-1/2 -translate-y-1/2 w-0.5 h-8 bg-[var(--border)] group-hover:bg-blue-500/60 rounded-full transition-colors" />
      </div>
    </div>
  );
}
