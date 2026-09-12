import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import { toCytoscapeElements, typeColor } from "../utils/validate.js";

/** Bounded Cytoscape rendering of API graph payloads.
 * No analytics are computed here — layout only.
 */
export default function NetworkGraph({ nodes, edges, onSelect, height, highlightIds }) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);
  const highlight = new Set(highlightIds || []);

  function buildElements() {
    return toCytoscapeElements(nodes, edges).map((el) =>
      // nodes have no `source`; edges do — flag only queried nodes.
      el.data.source === undefined && highlight.has(el.data.id)
        ? { data: { ...el.data, queried: true } }
        : el
    );
  }

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const cy = cytoscape({
      container: containerRef.current,
      elements: buildElements(),
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            color: "#0b1c30",
            "font-size": 10,
            "font-family": "Inter, sans-serif",
            "text-valign": "bottom",
            "text-margin-y": 4,
            width: 30,
            height: 30,
            "border-width": 2,
            "border-color": "#ffffff",
          },
        },
        {
          selector: "node:selected",
          style: {
            "border-width": 3,
            "border-color": "#4f46e5",
          },
        },
        {
          selector: "node[queried]",
          style: {
            "border-width": 4,
            "border-color": "#0b1c30",
            width: 36,
            height: 36,
          },
        },
        {
          selector: "edge",
          style: {
            label: "data(label)",
            "font-size": 8,
            color: "#64748b",
            "line-color": "#c7c4d8",
            width: 1.5,
            "target-arrow-shape": "triangle",
            "target-arrow-color": "#c7c4d8",
            "curve-style": "bezier",
          },
        },
      ],
      layout: { name: "cose", animate: false },
    });
    cyRef.current = cy;
    const handler = (event) => {
      if (onSelect) onSelect(event.target.id());
    };
    cy.on("tap", "node", handler);
    return () => {
      cy.removeListener("tap", "node", handler);
      cy.destroy();
      cyRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().remove();
    cy.add(buildElements());
    cy.layout({ name: "cose", animate: false }).run();
  }, [nodes, edges, highlightIds]);

  if (!nodes || nodes.length === 0) {
    return <p className="text-sm text-slate-500">No graph data to display.</p>;
  }

  const types = [...new Set((nodes || []).map((node) => node.type))];
  return (
    <div>
      <div
        ref={containerRef}
        style={{ height: height || 480 }}
        className="dot-grid w-full rounded-2xl border border-slate-200/80 bg-white"
        aria-label="Network graph"
      />
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-600">
        {types.map((type) => (
          <span key={type} className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-0.5 font-semibold">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: typeColor(type) }}
            />
            {type} ({nodes.filter((node) => node.type === type).length})
          </span>
        ))}
        <span className="ml-auto font-mono">
          {nodes.length} nodes · {edges ? edges.length : 0} edges (bounded view)
        </span>
      </div>
    </div>
  );
}
