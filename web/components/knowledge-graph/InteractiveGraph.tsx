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

function nodeRadius(level: number, connectionCount = 0): number {
  const base = [28, 20, 14, 10][level] ?? 10;
  // Scale up by connection count: +1px per 3 connections, max +8
  const bonus = Math.min(8, Math.floor(connectionCount / 3));
  return base + bonus;
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
  highlightedNodeId?: string | null;
  onNodeClick?: (node: KGNode) => void;
}

export function InteractiveGraph({ graph, kbName, highlightedNodeId = null, onNodeClick }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const minimapSvgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [stats, setStats] = useState<KGStats | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    fetchStats(kbName).then(setStats).catch(() => {});
  }, [kbName, graph]);

  // Listen for fullscreen changes
  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  }, []);

  const exportPng = useCallback(() => {
    if (!svgRef.current) return;
    const svgEl = svgRef.current;
    const w = svgEl.clientWidth;
    const h = svgEl.clientHeight;
    const svgData = new XMLSerializer().serializeToString(svgEl);
    const canvas = document.createElement("canvas");
    canvas.width = w * 2;
    canvas.height = h * 2;
    const ctx = canvas.getContext("2d")!;
    const img = new Image();
    const blob = new Blob(
      [`<?xml version="1.0" encoding="UTF-8"?>`, svgData],
      { type: "image/svg+xml;charset=utf-8" }
    );
    const url = URL.createObjectURL(blob);
    img.onload = () => {
      ctx.fillStyle = "#0f172a";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      const a = document.createElement("a");
      a.download = `knowledge-graph-${kbName || "export"}.png`;
      a.href = canvas.toDataURL("image/png");
      a.click();
    };
    img.src = url;
  }, [kbName]);

  const render = useCallback(() => {
    if (!svgRef.current || graph.nodes.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 600;

    // Container with zoom
    const g = svg.append("g");

    // Minimap update function (closure over nodes/links/width/height)
    // Will be filled in after node/link data is ready
    let updateMinimap = (_transform?: d3.ZoomTransform) => {};

    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 4])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
        updateMinimap(event.transform);
      });
    svg.call(zoom);

    // Disable default dblclick zoom so we can handle it ourselves
    svg.on("dblclick.zoom", null);

    // Detect literature graph mode
    const isLiterature = graph.nodes.some(
      (n) => (n as any).metadata?.graph_type === "literature"
    );

    // Count connections per node
    const connCount = new Map<string, number>();
    for (const e of graph.edges) {
      connCount.set(e.source_id, (connCount.get(e.source_id) || 0) + 1);
      connCount.set(e.target_id, (connCount.get(e.target_id) || 0) + 1);
    }

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
      .force("collision", d3.forceCollide<SimNode>().radius((d) => nodeRadius(d.level, connCount.get(d.id)) + 4));

    // Links
    const link = g.append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "#475569")
      .attr("stroke-opacity", 0.4)
      .attr("stroke-width", (d) => Math.max(1, d.weight * 2))
      .style("cursor", "pointer");

    // Edge hover tooltip (positioned relative to SVG element)
    const edgeTooltip = svg.append("g").style("display", "none").style("pointer-events", "none");
    const edgeTooltipBg = edgeTooltip.append("rect").attr("rx", 4).attr("fill", "#0f172a").attr("stroke", "#475569").attr("stroke-width", 1).attr("opacity", 0.9);
    const edgeTooltipText = edgeTooltip.append("text").attr("fill", "#94a3b8").attr("font-size", 11).attr("dy", "1em");

    link.on("mouseenter", function (event: MouseEvent, d) {
      if (!d.relation) return;
      d3.select(this).attr("stroke", "#94a3b8").attr("stroke-opacity", 0.9).attr("stroke-width", (d as SimLink).weight * 2 + 1);
      edgeTooltipText.text(d.relation);
      const bbox = edgeTooltipText.node()?.getBBox();
      if (!bbox) return;
      const padX = 8, padY = 5;
      edgeTooltipBg.attr("width", bbox.width + padX * 2).attr("height", bbox.height + padY * 2);
      edgeTooltipText.attr("x", padX).attr("y", padY);
      const svgRect = svgRef.current!.getBoundingClientRect();
      edgeTooltip.attr("transform", `translate(${event.clientX - svgRect.left + 10},${event.clientY - svgRect.top - 28})`);
      edgeTooltip.style("display", null);
    }).on("mousemove", function (event: MouseEvent) {
      const svgRect = svgRef.current!.getBoundingClientRect();
      edgeTooltip.attr("transform", `translate(${event.clientX - svgRect.left + 10},${event.clientY - svgRect.top - 28})`);
    }).on("mouseleave", function () {
      d3.select(this)
        .attr("stroke", "#475569")
        .attr("stroke-opacity", 0.4)
        .attr("stroke-width", (d) => Math.max(1, (d as SimLink).weight * 2));
      edgeTooltip.style("display", "none");
    });

    // Link labels for literature graphs
    const linkLabel = isLiterature
      ? g.append("g")
          .selectAll<SVGTextElement, SimLink>("text")
          .data(links.filter((l) => !["contains", "involved_in"].includes(l.relation)))
          .join("text")
          .attr("text-anchor", "middle")
          .attr("fill", "#64748b")
          .attr("font-size", 10)
          .attr("dy", -4)
          .text((d) => d.relation)
      : null;

    // Nodes
    const node = g.append("g")
      .selectAll<SVGGElement, SimNode>("g")
      .data(nodes)
      .join("g")
      .style("opacity", (d) => (highlightedNodeId && d.id !== highlightedNodeId ? 0.35 : 1))
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

    // Pulse ring for selected/highlighted node
    node.filter((d) => d.id === highlightedNodeId)
      .append("circle")
      .attr("class", "pulse-ring")
      .attr("r", (d) => nodeRadius(d.level, connCount.get(d.id)) + 8)
      .attr("fill", "none")
      .attr("stroke", "#3b82f6")
      .attr("stroke-width", 2);

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
            .attr("stroke", d.id === highlightedNodeId ? "#3b82f6" : "#1e293b")
            .attr("stroke-width", d.id === highlightedNodeId ? 3 : 1.5)
            .style("cursor", "pointer");
        } else {
          el.append("circle")
            .attr("r", r)
            .attr("fill", fill)
            .attr("stroke", d.id === highlightedNodeId ? "#3b82f6" : "#1e293b")
            .attr("stroke-width", d.id === highlightedNodeId ? 3 : 1.5)
            .style("cursor", "pointer");
        }
      });
    } else {
      node.append("circle")
        .attr("r", (d) => nodeRadius(d.level, connCount.get(d.id)))
        .attr("fill", (d) => nodeColor(d.mastery))
        .attr("stroke", (d) => (d.id === highlightedNodeId ? "#3b82f6" : "#1e293b"))
        .attr("stroke-width", (d) => (d.id === highlightedNodeId ? 3 : 1.5))
        .style("cursor", "pointer");
    }

    // Hover tooltip: label + mastery %
    const tooltip = g.append("g").style("display", "none").style("pointer-events", "none");
    const tooltipBg = tooltip.append("rect").attr("rx", 6).attr("fill", "#0f172a").attr("stroke", "#475569").attr("stroke-width", 1).attr("opacity", 0.95);
    const tooltipLabel = tooltip.append("text").attr("fill", "#f1f5f9").attr("font-size", 12).attr("font-weight", "600");
    const tooltipMastery = tooltip.append("text").attr("fill", "#64748b").attr("font-size", 11);
    const tooltipDot = tooltip.append("circle").attr("r", 4);

    node.on("mouseenter", function (_event, d) {
      const masteryPct = `${(d.mastery * 100).toFixed(0)}%`;
      tooltipLabel.text(d.label);
      tooltipMastery.text(`掌握度: ${masteryPct}`);
      tooltipDot.attr("fill", nodeColor(d.mastery));

      const labelBbox = tooltipLabel.node()?.getBBox() ?? { width: 0, height: 12 };
      const masteryBbox = tooltipMastery.node()?.getBBox() ?? { width: 0, height: 11 };
      const padX = 10, padY = 8, gap = 4;
      const contentW = Math.max(labelBbox.width, masteryBbox.width + 12);
      const totalW = contentW + padX * 2;
      const totalH = labelBbox.height + gap + masteryBbox.height + padY * 2;

      tooltipBg.attr("width", totalW).attr("height", totalH);
      tooltipLabel.attr("x", padX).attr("y", padY + labelBbox.height);
      tooltipDot.attr("cx", padX + 5).attr("cy", padY + labelBbox.height + gap + masteryBbox.height / 2 + 2);
      tooltipMastery.attr("x", padX + 14).attr("y", padY + labelBbox.height + gap + masteryBbox.height);

      const nr = nodeRadius(d.level, connCount.get(d.id));
      tooltip.attr("transform", `translate(${(d.x || 0) - totalW / 2},${(d.y || 0) - nr - totalH - 6})`);
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
        return nodeRadius(d.level, connCount.get(d.id)) + 14;
      })
      .attr("text-anchor", "middle")
      .attr("fill", (d) => (d.id === highlightedNodeId ? "#ffffff" : "#f8fafc"))
      .attr("font-weight", (d) => (d.id === highlightedNodeId ? 700 : 400))
      .attr("font-size", (d) => (d.level === 0 ? 12 : 10))
      .style("pointer-events", "none");

    // Single-click vs double-click discrimination
    let clickTimer: ReturnType<typeof setTimeout> | null = null;
    node.on("click", (_event, d) => {
      if (clickTimer) {
        clearTimeout(clickTimer);
        clickTimer = null;
        // Double-click: zoom into neighborhood
        const neighborIds = new Set([d.id]);
        for (const l of links) {
          const src = (l.source as SimNode).id;
          const tgt = (l.target as SimNode).id;
          if (src === d.id) neighborIds.add(tgt);
          if (tgt === d.id) neighborIds.add(src);
        }
        if (d.x != null && d.y != null) {
          svg.transition().duration(600).call(
            zoom.transform,
            d3.zoomIdentity
              .translate(width / 2, height / 2)
              .scale(Math.min(2.5, 4 / Math.sqrt(neighborIds.size)))
              .translate(-(d.x || 0), -(d.y || 0))
          );
        }
        return;
      }
      clickTimer = setTimeout(() => {
        clickTimer = null;
        const orig = graph.nodes.find((n) => n.id === d.id);
        if (orig && onNodeClick) onNodeClick(orig);
      }, 220);
    });

    if (highlightedNodeId) {
      const target = nodes.find((n) => n.id === highlightedNodeId);
      if (target?.x != null && target?.y != null) {
        const transform = d3.zoomIdentity
          .translate(width / 2, height / 2)
          .scale(1.35)
          .translate(-target.x, -target.y);
        svg.transition().duration(500).call(zoom.transform, transform);
      }
    }

    // Define minimap updater after nodes/links/dimensions are set
    updateMinimap = (transform?: d3.ZoomTransform) => {
      const mmEl = minimapSvgRef.current;
      if (!mmEl || nodes.length === 0) return;
      const mmSvg = d3.select(mmEl);
      const mmW = 140;
      const mmH = 100;

      const xs = nodes.map((n) => n.x ?? 0);
      const ys = nodes.map((n) => n.y ?? 0);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const rangeX = Math.max(maxX - minX, 1);
      const rangeY = Math.max(maxY - minY, 1);
      const pad = 10;
      const scale = Math.min((mmW - pad * 2) / rangeX, (mmH - pad * 2) / rangeY);
      const offX = pad + ((mmW - pad * 2) - rangeX * scale) / 2;
      const offY = pad + ((mmH - pad * 2) - rangeY * scale) / 2;

      const toX = (x: number) => (x - minX) * scale + offX;
      const toY = (y: number) => (y - minY) * scale + offY;

      mmSvg.selectAll("*").remove();
      // Background
      mmSvg.append("rect").attr("width", mmW).attr("height", mmH).attr("fill", "#0f172a").attr("rx", 6);

      // Edges
      mmSvg.append("g").selectAll("line").data(links).join("line")
        .attr("x1", (d) => toX((d.source as SimNode).x ?? 0))
        .attr("y1", (d) => toY((d.source as SimNode).y ?? 0))
        .attr("x2", (d) => toX((d.target as SimNode).x ?? 0))
        .attr("y2", (d) => toY((d.target as SimNode).y ?? 0))
        .attr("stroke", "#334155")
        .attr("stroke-width", 0.5);

      // Nodes
      mmSvg.append("g").selectAll("circle").data(nodes).join("circle")
        .attr("cx", (d) => toX(d.x ?? 0))
        .attr("cy", (d) => toY(d.y ?? 0))
        .attr("r", (d) => Math.max(1.5, nodeRadius(d.level, connCount.get(d.id)) * scale * 0.8))
        .attr("fill", (d) => nodeColor(d.mastery))
        .attr("opacity", (d) => d.id === highlightedNodeId ? 1 : 0.7);

      // Viewport rect
      if (transform) {
        const vx = -transform.x / transform.k;
        const vy = -transform.y / transform.k;
        const vw = width / transform.k;
        const vh = height / transform.k;
        mmSvg.append("rect")
          .attr("x", toX(vx))
          .attr("y", toY(vy))
          .attr("width", vw * scale)
          .attr("height", vh * scale)
          .attr("fill", "rgba(59,130,246,0.08)")
          .attr("stroke", "#3b82f6")
          .attr("stroke-width", 1.5)
          .attr("opacity", 0.8);
      }
    };

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
      updateMinimap();
    });

    return () => {
      simulation.stop();
    };
  }, [graph, highlightedNodeId, onNodeClick]);

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
    <div
      ref={containerRef}
      className="relative w-full h-full min-h-[500px] bg-[var(--background)] rounded-lg border border-[var(--border)]"
    >
      {/* Pulse animation */}
      <style>{`
        @keyframes pulse-ring {
          0%, 100% { opacity: 0.7; }
          50% { opacity: 0.15; }
        }
        .pulse-ring { animation: pulse-ring 1.6s ease-in-out infinite; }
      `}</style>

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

      {/* Top-right controls */}
      <div className="absolute top-3 right-3 z-10 flex gap-1.5">
        <button
          onClick={exportPng}
          title="导出为 PNG"
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded bg-[var(--card)]/90 backdrop-blur border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--card)] transition-colors"
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 12l-4-4h2.5V3h3v5H12L8 12z"/>
            <path d="M2 13h12v1.5H2z"/>
          </svg>
          导出
        </button>
        <button
          onClick={toggleFullscreen}
          title={isFullscreen ? "退出全屏" : "全屏"}
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded bg-[var(--card)]/90 backdrop-blur border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--card)] transition-colors"
        >
          {isFullscreen ? (
            <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
              <path d="M5.5 1v3.5H2V6h5V1H5.5zM10.5 1H9v5h5V4.5h-3.5V1zM2 10v1.5h3.5V15H7v-5H2zM9 10v5h1.5v-3.5H14V10H9z"/>
            </svg>
          ) : (
            <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
              <path d="M1 1h5v1.5H2.5V5H1V1zM10 1h5v4h-1.5V2.5H10V1zM1 11h1.5v2.5H5V15H1v-4zM13.5 13.5H10V15h5v-4h-1.5v2.5z"/>
            </svg>
          )}
          {isFullscreen ? "退出全屏" : "全屏"}
        </button>
      </div>

      <svg ref={svgRef} className="w-full h-full" />

      {/* Minimap */}
      {graph.nodes.length > 0 && (
        <div className="absolute bottom-3 right-3 z-10 rounded-lg border border-[var(--border)] overflow-hidden shadow-lg">
          <div className="px-2 py-0.5 text-[10px] text-[var(--muted-foreground)] bg-[var(--card)]/90 border-b border-[var(--border)]">
            全局视图
          </div>
          <svg ref={minimapSvgRef} width={140} height={100} />
        </div>
      )}

      {graph.nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-[var(--muted-foreground)]">
          暂无知识图谱数据
        </div>
      )}
    </div>
  );
}
