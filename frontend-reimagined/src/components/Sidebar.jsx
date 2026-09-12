import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { T, useLang } from "../i18n/LangContext.jsx";
import { STRINGS } from "../i18n/strings.js";
import GlobalSearch from "./GlobalSearch.jsx";

const LINKS = [
  { to: "/", end: true, icon: "dashboard", label: "nav_overview" },
  { to: "/network", icon: "hub", label: "nav_network" },
  { to: "/atlas", icon: "travel_explore", label: "nav_atlas" },
  { to: "/compare", icon: "compare_arrows", label: "nav_compare" },
  { to: "/anomalies", icon: "radar", label: "nav_anomalies" },
];

function railLinkClass({ isActive }) {
  return [
    "flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-white/15 text-white shadow-inner"
      : "text-indigo-100/70 hover:bg-white/10 hover:text-white",
  ].join(" ");
}

export default function Sidebar() {
  const { user, logout, isAdmin } = useAuth();
  const { lang, setLang, t } = useLang();
  const navigate = useNavigate();

  return (
    <aside className="argus-rail no-print flex w-64 shrink-0 flex-col text-white">
      <div className="px-5 pb-4 pt-6">
        <p className="text-lg font-extrabold tracking-wide">
          ARGUS <span className="font-light text-indigo-200">//</span>
        </p>
        <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-indigo-200/80">
          <T k="brand_sub" />
        </p>
        <p className="mt-2 inline-block rounded-md bg-white/10 px-2 py-0.5 font-mono text-[10px] text-indigo-100">
          <T k="demo_only" />
        </p>
      </div>

      {user ? (
        <div className="px-3">
          <GlobalSearch />
        </div>
      ) : null}

      <nav className="mt-2 flex flex-col gap-1 px-3">
        {LINKS.map((link) => (
          <NavLink key={link.to} to={link.to} end={link.end} className={railLinkClass}>
            <span className="material-symbols-outlined text-[20px]">{link.icon}</span>
            <T k={link.label} />
          </NavLink>
        ))}
        {isAdmin ? (
          <NavLink to="/users" className={railLinkClass}>
            <span className="material-symbols-outlined text-[20px]">group</span>
            <T k="nav_users" />
          </NavLink>
        ) : null}
      </nav>

      <div className="mt-2 px-3">
        <div className="flex rounded-xl bg-white/10 p-1 text-xs font-bold" role="group" aria-label="Language">
          {[{ v: "en", label: "EN" }, { v: "hi", label: "हिंदी" }].map((opt) => (
            <button
              key={opt.v}
              type="button"
              onClick={() => setLang(opt.v)}
              className={`flex-1 rounded-lg px-2 py-1.5 transition-colors ${
                lang === opt.v ? "bg-white text-argus-800" : "text-indigo-100/70 hover:text-white"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-auto px-5 pb-5">
        {user ? (
          <div className="rounded-xl bg-white/10 p-3">
            <p className="truncate text-xs font-semibold text-white">{user.email}</p>
            <p className="font-mono text-[10px] uppercase tracking-wider text-indigo-200">
              {user.role}
            </p>
              <button
              type="button"
              className="mt-2 w-full rounded-lg bg-white/15 px-3 py-1.5 text-xs font-semibold text-white hover:bg-white/25"
              onClick={() => {
                logout();
                navigate("/login");
              }}
            >
              <T k="sign_out" />
            </button>
          </div>
        ) : null}
        <p className="mt-3 font-mono text-[10px] leading-relaxed text-indigo-200/60">
          <T k="triage_note" />
        </p>
      </div>
    </aside>
  );
}
