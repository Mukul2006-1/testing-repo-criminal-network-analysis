import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../services/api.js";

/** Sidebar-wide entity search with a live result dropdown. */
export default function GlobalSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const boxRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    function onClick(event) {
      if (boxRef.current && !boxRef.current.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    const q = query.trim();
    if (q.length < 2) {
      setResults([]);
      setLoading(false);
      return undefined;
    }
    setLoading(true);
    timerRef.current = setTimeout(async () => {
      try {
        const data = await api.search(q, { page_size: 8 });
        setResults(data.items || data.entities || []);
        setOpen(true);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(timerRef.current);
  }, [query]);

  return (
    <div ref={boxRef} className="relative">
      <span className="material-symbols-outlined pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-indigo-200/70">
        search
      </span>
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => results.length && setOpen(true)}
        placeholder="Search entities…"
        className="w-full rounded-xl border border-white/10 bg-white/10 py-2 pl-9 pr-3 text-sm text-white placeholder:text-indigo-200/60 focus:border-white/30 focus:outline-none"
      />
      {open && (results.length > 0 || loading) ? (
        <ul className="absolute z-20 mt-2 max-h-72 w-72 overflow-auto rounded-xl border border-slate-200 bg-white p-1 shadow-card thin-scroll">
          {loading ? (
            <li className="px-3 py-2 text-xs text-slate-500">Searching…</li>
          ) : (
            results.map((row) => {
              const id = row.entity_id || row.id;
              return (
                <li key={id}>
                  <Link
                    to={`/entities/${encodeURIComponent(id)}`}
                    onClick={() => setOpen(false)}
                    className="block rounded-lg px-3 py-2 text-sm text-slate-800 hover:bg-argus-50"
                  >
                    <span className="font-semibold">{row.name || id}</span>{" "}
                    <span className="font-mono text-[11px] text-argus-700">({id})</span>
                  </Link>
                </li>
              );
            })
          )}
        </ul>
      ) : null}
    </div>
  );
}
