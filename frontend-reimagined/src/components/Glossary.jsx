/** Plain-language glossary: every analytical term gets an everyday name,
 * a one-line explanation, and an optional longer note. Rendered via <Term>.
 */

import { useLang } from "../i18n/LangContext.jsx";

export const TERMS = {
  pagerank: {
    plain: "Network influence",
    plain_hi: "नेटवर्क प्रभाव",
    short: "How well-connected this entity is to other well-connected entities.",
    short_hi: "यह एंटिटी अन्य प्रभावशाली एंटिटी से कितनी जुड़ी है।",
    long: "A high value means this entity sits among the most connected parts of the network. It describes position, not behaviour.",
  },
  betweenness: {
    plain: "Bridge role",
    plain_hi: "सेतु भूमिका",
    short: "How often this entity lies on paths between other entities.",
    short_hi: "अन्य एंटिटी के बीच के रास्ते कितनी बार इससे होकर जाते हैं।",
    long: "A high value means separate groups mostly connect through this entity — removing it would split the network.",
  },
  anomaly: {
    plain: "Unusual-pattern flag",
    plain_hi: "असामान्य पैटर्न चेतावनी",
    short: "How far this entity's behaviour deviates from its usual pattern.",
    short_hi: "इसका व्यवहार सामान्य पैटर्न से कितना अलग है।",
    long: "Computed by comparing calls, transactions and locations against typical behaviour. A flag is a lead, never proof of wrongdoing.",
  },
  priority: {
    plain: "Review priority",
    plain_hi: "समीक्षा प्राथमिकता",
    short: "Suggested order for investigator review (0–1, higher first).",
    short_hi: "जांचकर्ता समीक्षा का सुझाया क्रम (0–1, अधिक पहले)।",
    long: "Combines network influence (35%), bridge role (35%) and unusual-pattern flag (30%). A triage aid — not a probability of guilt.",
  },
  community: {
    plain: "Close-knit group",
    plain_hi: "घनिष्ठ समूह",
    short: "A cluster of entities that interact far more with each other than with outsiders.",
    short_hi: "एंटिटी का समूह जो आपस में बाहर वालों से अधिक जुड़ा है।",
  },
  severity: {
    plain: "Flag level",
    plain_hi: "चेतावनी स्तर",
    short: "How strong the unusual pattern is: Critical, High, Medium or Low.",
    short_hi: "असामान्य पैटर्न कितना गंभीर है: गंभीर, उच्च, मध्यम या निम्न।",
  },
  degree: {
    plain: "Direct connections",
    plain_hi: "प्रत्यक्ष संबंध",
    short: "How many direct links this entity has.",
    short_hi: "इस एंटिटी के कितने प्रत्यक्ष संबंध हैं।",
  },
  resolution: {
    plain: "Same-entity matching",
    plain_hi: "समान-एंटिटी मिलान",
    short: "How different spellings (e.g. 'R. Sharma' vs 'Rahul Sharma') are recognised as one person when they share evidence like a phone number.",
    short_hi: "साझा साक्ष्य (जैसे फ़ोन नंबर) होने पर अलग-अलग वर्तनी एक ही व्यक्ति कैसे मानी जाती है।",
  },
};

/** Dotted-underline term with a hover tooltip. Usage: <Term k="pagerank" /> */
export default function Term({ k, children }) {
  const { lang } = useLang();
  const entry = TERMS[k];
  if (!entry) return <>{children || k}</>;
  const hi = lang === "hi";
  const plain = hi && entry.plain_hi ? entry.plain_hi : entry.plain;
  const short = hi && entry.short_hi ? entry.short_hi : entry.short;
  return (
    <span className="group relative inline-block cursor-help border-b border-dotted border-argus-400">
      {children || plain}
      <span className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-2 hidden w-64 -translate-x-1/2 rounded-xl border border-slate-200 bg-ink p-3 text-xs font-normal leading-relaxed text-white shadow-card group-hover:block">
        <span className="font-bold text-argus-200">{plain}</span>
        <br />
        {short}
        {!hi && entry.long ? (
          <>
            <br />
            <span className="text-slate-300">{entry.long}</span>
          </>
        ) : null}
      </span>
    </span>
  );
}
