/** Plain-language glossary: every analytical term gets an everyday name,
 * a one-line explanation, and an optional longer note. Rendered via <Term>.
 */

export const TERMS = {
  pagerank: {
    plain: "Network influence",
    short: "How well-connected this entity is to other well-connected entities.",
    long: "A high value means this entity sits among the most connected parts of the network. It describes position, not behaviour.",
  },
  betweenness: {
    plain: "Bridge role",
    short: "How often this entity lies on paths between other entities.",
    long: "A high value means separate groups mostly connect through this entity — removing it would split the network.",
  },
  anomaly: {
    plain: "Unusual-pattern flag",
    short: "How far this entity's behaviour deviates from its usual pattern.",
    long: "Computed by comparing calls, transactions and locations against typical behaviour. A flag is a lead, never proof of wrongdoing.",
  },
  priority: {
    plain: "Review priority",
    short: "Suggested order for investigator review (0–1, higher first).",
    long: "Combines network influence (35%), bridge role (35%) and unusual-pattern flag (30%). A triage aid — not a probability of guilt.",
  },
  community: {
    plain: "Close-knit group",
    short: "A cluster of entities that interact far more with each other than with outsiders.",
  },
  severity: {
    plain: "Flag level",
    short: "How strong the unusual pattern is: Critical, High, Medium or Low.",
  },
  degree: {
    plain: "Direct connections",
    short: "How many direct links this entity has.",
  },
  resolution: {
    plain: "Same-entity matching",
    short: "How different spellings (e.g. 'R. Sharma' vs 'Rahul Sharma') are recognised as one person when they share evidence like a phone number.",
  },
};

/** Dotted-underline term with a hover tooltip. Usage: <Term k="pagerank" /> */
export default function Term({ k, children }) {
  const entry = TERMS[k];
  if (!entry) return <>{children || k}</>;
  return (
    <span className="group relative inline-block cursor-help border-b border-dotted border-argus-400">
      {children || entry.plain}
      <span className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-2 hidden w-64 -translate-x-1/2 rounded-xl border border-slate-200 bg-ink p-3 text-xs font-normal leading-relaxed text-white shadow-card group-hover:block">
        <span className="font-bold text-argus-200">{entry.plain}</span>
        <br />
        {entry.short}
        {entry.long ? (
          <>
            <br />
            <span className="text-slate-300">{entry.long}</span>
          </>
        ) : null}
      </span>
    </span>
  );
}
