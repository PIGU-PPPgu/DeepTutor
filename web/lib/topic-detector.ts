import type { KGGraph } from "@/components/knowledge-graph/graph-api";

/**
 * Detect knowledge topics mentioned in a message by matching node labels.
 * Sorts by label length (longer matches first) to prefer more specific terms.
 */
export function detectTopics(message: string, graphData: KGGraph | null): string[] {
  if (!graphData) return [];
  const lower = message.toLowerCase();
  const topics: string[] = [];
  for (const node of graphData.nodes) {
    if (lower.includes(node.label.toLowerCase())) {
      topics.push(node.label);
    }
  }
  // Deduplicate, prefer longer labels
  const unique = [...new Set(topics)];
  unique.sort((a, b) => b.length - a.length);
  return unique.slice(0, 8);
}
