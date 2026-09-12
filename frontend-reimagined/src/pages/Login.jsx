import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";

const FEATURES = [
  { icon: "hub", title: "Knowledge Graph", text: "Entities and relationships resolved into one canonical graph." },
  { icon: "radar", title: "Anomaly Detection", text: "Isolation Forest flags unusual communication and transaction patterns." },
  { icon: "insights", title: "Explainable Priority", text: "Every score ships with component contributions and source evidence." },
];

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(username.trim(), password);
      navigate(location.state?.from || "/", { replace: true });
    } catch (err) {
      setError(err.message || "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-card lg:grid lg:grid-cols-2">
      <div className="argus-rail relative hidden p-10 text-white lg:block">
        <p className="text-xl font-extrabold tracking-wide">
          ARGUS <span className="font-light text-indigo-200">//</span>
        </p>
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-indigo-200/80">
          Crime Network Intelligence
        </p>
        <p className="mt-2 text-sm text-indigo-100/80">
          Autonomous link analysis and pattern discovery engine.
        </p>
        <div className="mt-8 space-y-4">
          {FEATURES.map((feature) => (
            <div key={feature.title} className="rounded-xl bg-white/10 p-4">
              <p className="flex items-center gap-2 text-sm font-bold">
                <span className="material-symbols-outlined text-[20px]">{feature.icon}</span>
                {feature.title}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-indigo-100/75">{feature.text}</p>
            </div>
          ))}
        </div>
        <p className="absolute bottom-6 font-mono text-[11px] text-indigo-200/60">
          ● Synthetic demo data only
        </p>
      </div>

      <div className="dot-grid p-8 sm:p-10">
        <h1 className="text-2xl font-extrabold text-ink">Sign in to your console</h1>
        <p className="mt-1 text-sm text-slate-500">
          Use credentials created by your administrator
          (<span className="font-mono text-xs">scripts/create_admin.py</span>).
        </p>
        <form className="mt-6 space-y-4" onSubmit={submit}>
          <label className="block text-sm">
            <span className="font-semibold text-slate-600">Work email</span>
            <input
              className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 focus:border-argus-500 focus:outline-none focus:ring-2 focus:ring-argus-100"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              placeholder="analyst@example.local"
            />
          </label>
          <label className="block text-sm">
            <span className="font-semibold text-slate-600">Password</span>
            <input
              className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 focus:border-argus-500 focus:outline-none focus:ring-2 focus:ring-argus-100"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
          </label>
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <button
            className="w-full rounded-xl bg-argus-600 px-3 py-2.5 text-sm font-bold text-white hover:bg-argus-700 disabled:opacity-50"
            type="submit"
            disabled={busy}
          >
            {busy ? "Signing in…" : "Access Secure Console →"}
          </button>
        </form>
        <p className="mt-6 rounded-xl bg-amber-50 p-3 text-xs leading-relaxed text-amber-800">
          Decision-support tool. Scores are investigation triage aids, not verdicts —
          they never imply guilt or predict crime.
        </p>
      </div>
    </main>
  );
}
