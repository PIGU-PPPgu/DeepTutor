"use client";

import { useState, useMemo, useCallback } from "react";
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

  // Create all tree nodes
  for (const n of nodes) {
    map.set(n.id, { node: n, children: [] });
  }

  // Build parent-child relationships
  for (const n of nodes) {
    const tn = map.get(n.id)!;
    if (n.parent_id && map.has(n.parent_id)) {
      map.get(n.parent_id)!.children.push(tn);
    } else {
      roots.push(tn);
    }
  }

  // Sort children by label
  const sortChildren = (t: TreeNode) => {
    t.children.sort((a, b) => a.node.label.localeCompare(b.node.label, "zh"));
    t.children.forEach(sortChildren);
  };
  roots.sort((a, b) => a.node.label.localeCompare(b.node.label, "zh"));
  roots.forEach(sortChildren);

  return roots;
}

/** Get IDs of all ancestors for a set of matched node IDs */
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
  // Include ancestors
  const ancestors = getAncestorIds(nodes, matched);
  for (const a of ancestors) matched.add(a);
  return matched;
}

function TreeRow({
  treeNode,
  depth,
  selectedNodeId,
  onSelect,
  expandedIds,
  toggleExpand,
  visibleIds,
}: {
  treeNode: TreeNode;
  depth: number;
  selectedNodeId: string | null;
  onSelect: (nodeId: string) => void;
  expandedIds: Set<string>;
  toggleExpand: (id: string) => void;
  visibleIds: Set<string>;
}) {
  const { node, children } = treeNode;
  const isSelected = selectedNodeId === node.id;
  const hasChildren = children.length > 0;
  const isExpanded = expandedIds.has(node.id);
  const childCount = children.length;

  if (!visibleIds.has(node.id)) return null;

  // Only show children that are visible
  const visibleChildren = children.filter((c) => visibleIds.has(c.node.id));
  const showChildren = hasChildren && isExpanded && visibleChildren.length > 0;

  return (
    <>
      <div
        className={`group flex items-center gap-1.5 px-2 py-1 cursor-pointer hover:bg-white/5 transition-colors ${
          isSelected ? "bg-blue-500/15" : ""
        }`}
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
        onClick={() => onSelect(node.id)}
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
        <span className="text-sm text-white truncate flex-1">{node.label}</span>

        {/* Child count */}
        {hasChildren && childCount > 0 && (
          <span className="text-[10px] text-[var(--muted-foreground)] shrink-0">
            {childCount}
          </span>
        )}
      </div>

      {/* Children with animation */}
      <div
        className="overflow-hidden transition-all duration-200"
        style={{
          maxHeight: showChildren ? `${visibleChildren.length * 32}px` : "0px",
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
              onSelect={onSelect}
              expandedIds={expandedIds}
              toggleExpand={toggleExpand}
              visibleIds={visibleIds}
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

  // Auto-expand on search: expand all visible ancestor nodes
  const autoExpandedIds = useMemo(() => {
    if (!searchQuery.trim()) return new Set<string>();
    const expanded = new Set<string>();
    // Any node that has visible children should be expanded
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

  const [manualExpanded, setManualExpanded] = useState<Set<string>>(new Set());

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

  return (
    <div className="w-[280px] shrink-0 bg-[var(--card)] border-r border-[var(--border)] flex flex-col h-full">
      {/* Search */}
      <div className="p-3 border-b border-[var(--border)]">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="搜索知识点..."
          className="w-full px-3 py-1.5 text-sm rounded bg-[var(--secondary)] text-[var(--foreground)] border border-[var(--border)] placeholder:text-[var(--muted-foreground)] outline-none focus:border-blue-500"
        />
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto py-1">
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
              onSelect={onSelect}
              expandedIds={expandedIds}
              toggleExpand={toggleExpand}
              visibleIds={visibleIds}
            />
          ))
        )}
      </div>

      {/* Footer */}
      <div className="px-3 py-2 border-t border-[var(--border)] text-xs text-[var(--muted-foreground)]">
        共 {nodes.length} 个节点
      </div>
    </div>
  );
}
