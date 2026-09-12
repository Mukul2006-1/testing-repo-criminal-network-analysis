import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import GlobalSearch from "./GlobalSearch.jsx";

const LINKS = [
  { to: "/", end: true, icon: "dashboard", label: "Overview" },
  { to: "/network", icon: "hub", label: "Network" },
  { to: "/atlas", icon: "travel_explore", label: "Atlas" },
  { to: "/compare", icon: "compare_arrows", label: "Rel. check" },
  { to: "/anomalies", icon: "radar", label: "Anomalies" },
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
  const navigate = useNavigate();

  return (
    <aside className="argus-rail no-print flex w-64 shrink-0 flex-col text-white">
      <div className="px-5 pb-4 pt-6">
        <p className="text-lg font-extrabold tracking-wide">
          ARGUS <span className="font-light text-indigo-200">//</span>
        </p>
        <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-indigo-200/80">
          Network Intelligence
        </p>
        <p className="mt-2 inline-block rounded-md bg-white/10 px-2 py-0.5 font-mono text-[10px] text-indigo-100">
          Synthetic demo data only
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
            {link.label}
          </NavLink>
        ))}
        {isAdmin ? (
          <NavLink to="/users" className={railLinkClass}>
            <span className="material-symbols-outlined text-[20px]">group</span>
            Users
          </NavLink>
        ) : null}
      </nav>

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
              Sign out
            </button>
          </div>
        ) : null}
        <p className="mt-3 font-mono text-[10px] leading-relaxed text-indigo-200/60">
          Scores are triage signals,
          <br />
          not verdicts.
        </p>
      </div>
    </aside>
  );
}
