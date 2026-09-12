import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import { toCytoscapeElements, typeColor } from "../utils/validate.js";

/** Bounded Cytoscape rendering of API graph payloads.
 * No analytics are computed here — layout only.
 */
export default function NetworkGraph({ nodes, edges, onSelect, height }) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const cy = cytoscape({
      container: containerRef.current,
      elements: toCytoscapeElements(nodes, edges),
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            color: "#111827",
            "font-size": 10,
            "text-valign": "bottom",
            "text-margin-y": 4,
            width: 28,
            height: 28,
          },
        },
        {
          selector: "edge",
          style: {
            label: "data(label)",
            "font-size": 8,
            color: "#6b7280",
            "line-color": "#9ca3af",
            width: 1.5,
            "target-arrow-shape": "triangle",
            "target-arrow-color": "#9ca3af",
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
    cy.add(toCytoscapeElements(nodes, edges));
    cy.layout({ name: "cose", animate: false }).run();
  }, [nodes, edges]);

  if (!nodes || nodes.length === 0) {
    return <p className="text-sm text-gray-500">No graph data to display.</p>;
  }

  const types = [...new Set((nodes || []).map((node) => node.type))];
  return (
    <div>
      <div
        ref={containerRef}
        style={{ height: height || 480 }}
        className="w-full rounded border border-gray-200 bg-white"
        aria-label="Network graph"
      />
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-600">
        {types.map((type) => (
          <span key={type} className="inline-flex items-center gap-1">
            <span
              className="inline-block h-3 w-3 rounded-full"
              style={{ backgroundColor: typeColor(type) }}
            />
            {type} ({nodes.filter((node) => node.type === type).length})
          </span>
        ))}
        <span className="ml-auto">
          {nodes.length} nodes · {edges ? edges.length : 0} edges (bounded view)
        </span>
      </div>
    </div>
  );
}
