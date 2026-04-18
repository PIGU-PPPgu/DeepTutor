/** Knowledge Graph API client */

import { apiUrl } from "@/lib/api";

export interface KGNode {
  id: string;
  label: string;
  description: string;
  parent_id: string | null;
  level: number;
  mastery: number;
  source: string;
  metadata: Record<string, unknown>;
}

export interface KGEdge {
  source_id: string;
  target_id: string;
  relation: string;
  weight: number;
}

export interface KGGraph {
  nodes: KGNode[];
  edges: KGEdge[];
}

export interface KGStats {
  total: number;
  mastered: number;
  learning: number;
  unstudied: number;
  weak: number;
  mastery_avg: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const err = await res.text().catch(() => res.statusText);
    throw new Error(`KG API ${res.status}: ${err}`);
  }
  return res.json();
}

export function fetchGraph(kbName: string): Promise<KGGraph> {
  return request<KGGraph>(`/api/v1/knowledge-graph/${encodeURIComponent(kbName)}`);
}

export function fetchStats(kbName: string): Promise<KGStats> {
  return request<KGStats>(`/api/v1/knowledge-graph/${encodeURIComponent(kbName)}/stats`);
}

export function generateGraph(kbName: string, content: string): Promise<KGGraph> {
  return request<KGGraph>(`/api/v1/knowledge-graph/${encodeURIComponent(kbName)}/generate`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function updateMastery(kbName: string, nodeId: string, mastery: number, source?: string): Promise<KGNode> {
  return request<KGNode>(`/api/v1/knowledge-graph/${encodeURIComponent(kbName)}/nodes/${encodeURIComponent(nodeId)}`, {
    method: "PATCH",
    body: JSON.stringify({ mastery, source }),
  });
}

export function getWeakNodes(kbName: string, threshold = 0.3): Promise<{ nodes: KGNode[] }> {
  return request(`/api/v1/knowledge-graph/${encodeURIComponent(kbName)}/weak?threshold=${threshold}`);
}

export function expandGraph(kbName: string, maxDepth = 5, targetNodes = 1500): Promise<{ nodes: number; edges: number; graph: KGGraph }> {
  return request(`/api/v1/knowledge-graph/${encodeURIComponent(kbName)}/expand`, {
    method: "POST",
    body: JSON.stringify({ max_depth: maxDepth, target_nodes: targetNodes }),
  });
}

export function listGraphs(): Promise<{ graphs: string[] }> {
  return request("/api/v1/knowledge-graph");
}
