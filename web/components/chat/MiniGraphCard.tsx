"use client";

import { useEffect, useRef, useCallback } from "react";
import * as d3 from "d3";
import { fetchGraph, type KGGraph, type KGNode, type KGEdge } from "@/components/knowledge-graph/graph-api";

interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  label: string;
  mastery: number;
  level: number;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  relation: string;
}

function nodeColor(mastery: number): string {
  if (mastery >= 0.8) return "#22c55e";
  if (mastery >= 0.3) return "#eab308";
  if (mastery > 0) return "#ef4444";
  return "#94a3b8";
}

interface Props {
  topics: string[];
  kbName: string;
}

/**
 * Mini graph card showing a local neighborhood of topics mentioned in chat.
 * Renders a small D3 force-directed graph (~200px tall).
 */
export function MiniGraphCard({ topics, kbName }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const render = useCallback(async () => {
    if (!svgRef.current || !topics.length) return;

    let graph: KGGraph;
    try {
      graph = await fetchGraph(kbName);
    } catch {
      return;
    }

    // Find nodes matching topics (case-insensitive)
    const lowerTopics = topics.map((t) => t.toLowerCase());
    const matchedNodes = graph.nodes.filter((n) =>
      lowerTopics.some((t) => n.label.toLowerCase().includes(t) || t.includes(n.label.toLowerCase()))
    );

    if (!matchedNodes.length) return;

    const matchedIds = new Set(matchedNodes.map((n) => n.id));

    // Add 1-hop neighbors
    const neighborIds = new Set<string>(matchedIds);
    for (const e of graph.edges) {
      if (matchedIds.has(e.source_id)) neighborIds.add(e.target_id);
      if (matchedIds.has(e.target_id)) neighborIds.add(e.source_id);
    }

    // Limit to ~15 nodes for readability
    const limitedIds = new Set([...neighborIds].slice(0, 15));
    const filteredNodes = graph.nodes.filter((n) => limitedIds.has(n.id));
    const nodeMap = new Map(filteredNodes.map((n) => [n.id, n]));

    const simNodes: SimNode[] = filteredNodes.map((n) => ({
      id: n.id, label: n.label, mastery: n.mastery, level: n.level,
    }));
    const simLinks: SimLink[] = graph.edges
      .filter((e) => nodeMap.has(e.source_id) && nodeMap.has(e.target_id))
      .map((e) => ({ source: e.source_id, target: e.target_id, relation: e.relation }));

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const width = svgRef.current.clientWidth || 280;
    const height = svgRef.current.clientHeight || 200;

    const g = svg.append("g");

    const simulation = d3
      .forceSimulation<SimNode>(simNodes)
      .force("link", d3.forceLink<SimNode, SimLink>(simLinks).id((d) => d.id).distance(50))
      .force("charge", d3.forceManyBody().strength(-120))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide<SimNode>().radius(12));

    const link = g
      .append("g")
      .selectAll("line")
      .data(simLinks)
      .join("line")
      .attr("stroke", "#475569")
      .attr("stroke-opacity", 0.3)
      .attr("stroke-width", 1);

    const node = g
      .append("g")
      .selectAll<SVGGElement, SimNode>("g")
      .data(simNodes)
      .join("g")
      .call(
        d3
          .drag<SVGGElement, SimNode>()
          .on("start", (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );

    node
      .append("circle")
      .attr("r", (d) => (matchedIds.has(d.id) ? 10 : 7))
      .attr("fill", (d) => nodeColor(d.mastery))
      .attr("stroke", "#1e293b")
      .attr("stroke-width", 1)
      .style("cursor", "pointer");

    node
      .append("text")
      .text((d) => d.label)
      .attr("dy", (d) => (matchedIds.has(d.id) ? 16 : 13))
      .attr("text-anchor", "middle")
      .attr("fill", "#f8fafc")
      .attr("font-size", 9)
      .style("pointer-events", "none");

    simulation.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as SimNode).x!)
        .attr("y1", (d) => (d.source as SimNode).y!)
        .attr("x2", (d) => (d.target as SimNode).x!)
        .attr("y2", (d) => (d.target as SimNode).y!);
      node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
    };
  }, [topics, kbName]);

  useEffect(() => {
    let cleanup: (() => void) | undefined;
    render().then((c) => {
      cleanup = c;
    });
    return () => cleanup?.();
  }, [render]);

  return (
    <div
      ref={containerRef}
      className="mt-2 rounded-xl border border-[var(--border)] bg-[var(--card)]/80 overflow-hidden"
    >
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-[var(--border)]">
        <span className="text-[10px] font-medium text-[var(--muted-foreground)]">
          📊 相关知识图谱
        </span>
        <a
          href="/graph"
          className="text-[10px] text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
        >
          查看完整图谱 →
        </a>
      </div>
      <svg ref={svgRef} className="w-full" style={{ height: 200 }} />
    </div>
  );
}
