"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import type { SimulationNodeDatum, SimulationLinkDatum } from "d3";
import type { KGGraph, KGNode, KGStats } from "./graph-api";
import { fetchStats } from "./graph-api";

interface SimNode extends SimulationNodeDatum {
  id: string;
  label: string;
  level: number;
  mastery: number;
  description: string;
  parent_id: string | null;
  expanded: boolean;
  metadata?: Record<string, string>;
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  relation: string;
  weight: number;
  metadata?: Record<string, string>;
}

function nodeColor(mastery: number): string {
  if (mastery >= 0.8) return "#22c55e";
  if (mastery >= 0.3) return "#eab308";
  if (mastery > 0) return "#ef4444";
  return "#94a3b8";
}

function nodeRadius(level: number): number {
  return [28, 20, 14, 10][level] ?? 10;
}

function groupColor(group: string): string {
  const palette = ["#6366f1", "#ec4899", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6", "#ef4444", "#14b8a6"];
  let hash = 0;
  for (let i = 0; i < group.length; i++) hash = group.charCodeAt(i) + ((hash << 5) - hash);
  return palette[Math.abs(hash) % palette.length];
}

interface Props {
  graph: KGGraph;
  kbName: string;
  onNodeClick?: (node: KGNode) => void;
}

export function InteractiveGraph({ graph, kbName, onNodeClick }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [stats, setStats] = useState<KGStats | null>(null);

  useEffect(() => {
    fetchStats(kbName).then(setStats).catch(() => {});
  }, [kbName, graph]);

  const render = useCallback(() => {
    if (!svgRef.current || graph.nodes.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 600;

    // Container with zoom
    const g = svg.append("g");

    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 4])
      .on("zoom", (event) => g.attr("transform", event.transform));
    svg.call(zoom);

    // Detect literature graph mode
    const isLiterature = graph.nodes.some(
      (n) => (n as any).metadata?.graph_type === "literature"
    );

    // Build simulation data
    const nodeMap = new Map<string, SimNode>();
    const nodes: SimNode[] = graph.nodes.map((n) => {
      const sn: SimNode = {
        ...n,
        expanded: true,
        metadata: (n as any).metadata as Record<string, string> | undefined,
      };
      nodeMap.set(n.id, sn);
      return sn;
    });

    const links: SimLink[] = graph.edges
      .filter((e) => nodeMap.has(e.source_id) && nodeMap.has(e.target_id))
      .map((e) => ({
        source: e.source_id,
        target: e.target_id,
        relation: e.relation,
        weight: e.weight,
        metadata: (e as any).metadata as Record<string, string> | undefined,
      }));

    const simulation = d3.forceSimulation<SimNode>(nodes)
      .force("link", d3.forceLink<SimNode, SimLink>(links).id((d) => d.id).distance(80))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide<SimNode>().radius((d) => nodeRadius(d.level) + 4));

    // Links
    const link = g.append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "#475569")
      .attr("stroke-opacity", 0.4)
      .attr("stroke-width", (d) => Math.max(1, d.weight * 2));

    // Link labels for literature graphs
    const linkLabel = isLiterature
      ? g.append("g")
          .selectAll<SVGTextElement, SimLink>("text")
          .data(links.filter((l) => !["contains", "involved_in"].includes(l.relation)))
          .join("text")
          .attr("text-anchor", "middle")
          .attr("fill", "#94a3b8")
          .attr("font-size", 9)
          .attr("dy", -4)
          .text((d) => d.relation)
      : null;

    // Nodes
    const node = g.append("g")
      .selectAll<SVGGElement, SimNode>("g")
      .data(nodes)
      .join("g")
      .call(
        d3.drag<SVGGElement, SimNode>()
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
          }),
      );

    // Shape by literature type
    if (isLiterature) {
      node.each(function (d) {
        const el = d3.select(this);
        const charType = d.metadata?.type || "supporting";
        const group = d.metadata?.group || "";
        const fill = group ? groupColor(group) : nodeColor(d.mastery);
        const r = d.level === 0 ? 28 : charType === "protagonist" ? 22 : charType === "antagonist" ? 18 : 12;

        if (charType === "antagonist" && d.level !== 0) {
          el.append("polygon")
            .attr("points", `0,${-r} ${r},0 0,${r} ${-r},0`)
            .attr("fill", fill)
            .attr("stroke", "#1e293b")
            .attr("stroke-width", 1.5)
            .style("cursor", "pointer");
        } else {
          el.append("circle")
            .attr("r", r)
            .attr("fill", fill)
            .attr("stroke", "#1e293b")
            .attr("stroke-width", 1.5)
            .style("cursor", "pointer");
        }
      });
    } else {
      node.append("circle")
        .attr("r", (d) => nodeRadius(d.level))
        .attr("fill", (d) => nodeColor(d.mastery))
        .attr("stroke", "#1e293b")
        .attr("stroke-width", 1.5)
        .style("cursor", "pointer");
    }

    // Tooltip on hover
    const tooltip = g.append("g").style("display", "none");
    const tooltipBg = tooltip.append("rect").attr("rx", 4).attr("fill", "#1e293b").attr("opacity", 0.9);
    const tooltipText = tooltip.append("text").attr("fill", "#e2e8f0").attr("font-size", 11).attr("dy", "0.35em");

    node.on("mouseenter", function (_event, d) {
      if (!d.description) return;
      tooltipText.text(d.description.length > 60 ? d.description.slice(0, 60) + "\u2026" : d.description);
      const bbox = tooltipText.node()?.getBBox();
      if (!bbox) return;
      tooltipBg.attr("width", bbox.width + 12).attr("height", bbox.height + 8);
      tooltip.attr("transform", `translate(${d.x!},${(d.y || 0) - 30})`);
      tooltip.style("display", null);
    }).on("mouseleave", () => {
      tooltip.style("display", "none");
    });

    node.append("text")
      .text((d) => d.label)
      .attr("dy", (d) => {
        if (isLiterature) {
          const t = d.metadata?.type || "";
          const r = d.level === 0 ? 28 : t === "protagonist" ? 22 : t === "antagonist" ? 18 : 12;
          return r + 14;
        }
        return nodeRadius(d.level) + 14;
      })
      .attr("text-anchor", "middle")
      .attr("fill", "#e2e8f0")
      .attr("font-size", (d) => (d.level === 0 ? 12 : 10))
      .style("pointer-events", "none");

    node.on("click", (_event, d) => {
      const orig = graph.nodes.find((n) => n.id === d.id);
      if (orig && onNodeClick) onNodeClick(orig);
    });

    simulation.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as SimNode).x!)
        .attr("y1", (d) => (d.source as SimNode).y!)
        .attr("x2", (d) => (d.target as SimNode).x!)
        .attr("y2", (d) => (d.target as SimNode).y!);
      if (linkLabel) {
        linkLabel
          .attr("x", (d) => ((d.source as SimNode).x! + (d.target as SimNode).x!) / 2)
          .attr("y", (d) => ((d.source as SimNode).y! + (d.target as SimNode).y!) / 2);
      }
      node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
    };
  }, [graph, onNodeClick]);

  useEffect(() => {
    const cleanup = render();
    return () => cleanup?.();
  }, [render]);

  // Resize observer
  useEffect(() => {
    if (!svgRef.current) return;
    const ro = new ResizeObserver(() => render());
    ro.observe(svgRef.current);
    return () => ro.disconnect();
  }, [render]);

  return (
    <div className="relative w-full h-full min-h-[500px] bg-[var(--background)] rounded-lg border border-[var(--border)]">
      {/* Legend */}
      <div className="absolute top-3 left-3 z-10 bg-[var(--card)]/90 backdrop-blur rounded-lg p-3 text-xs space-y-1.5 border border-[var(--border)]">
        <div className="font-semibold text-[var(--foreground)] mb-1">掌握度</div>
        {[
          { color: "#22c55e", label: "已掌握 (≥80%)" },
          { color: "#eab308", label: "学习中 (30-80%)" },
          { color: "#ef4444", label: "薄弱 (<30%)" },
          { color: "#94a3b8", label: "未学习" },
        ].map(({ color, label }) => (
          <div key={color} className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-full" style={{ background: color }} />
            <span className="text-[var(--muted-foreground)]">{label}</span>
          </div>
        ))}
        {stats && (
          <div className="mt-2 pt-2 border-t border-[var(--border)] text-[var(--muted-foreground)]">
            <div>总计: {stats.total} 个知识点</div>
            <div>平均掌握: {(stats.mastery_avg * 100).toFixed(0)}%</div>
          </div>
        )}
      </div>

      <svg ref={svgRef} className="w-full h-full" />

      {graph.nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-[var(--muted-foreground)]">
          暂无知识图谱数据
        </div>
      )}
    </div>
  );
}
