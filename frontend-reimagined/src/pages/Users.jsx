import { useEffect, useState } from "react";
import { ApiError, api } from "../services/api.js";
import Card from "../components/Card.jsx";
import { T } from "../i18n/LangContext.jsx";

const ROLES = ["INVESTIGATOR", "SENIOR_INVESTIGATOR", "ADMIN"];

function roleBadge(role) {
  const tone =
    role === "ADMIN"
      ? "bg-argus-100 text-argus-800"
      : role === "SENIOR_INVESTIGATOR"
        ? "bg-sky-100 text-sky-800"
        : "bg-slate-100 text-slate-600";
  return (
    <span className={`rounded-full px-2.5 py-0.5 font-mono text-[11px] font-bold ${tone}`}>
      {role}
    </span>
  );
}

export default function Users() {
  const [users, setUsers] = useState([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "INVESTIGATOR" });
  const [notice, setNotice] = useState("");

  async function load() {
    setError("");
    try {
      const data = await api.listUsers();
      setUsers(data.items || []);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Load failed.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function create(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      await api.createUser(form);
      setNotice(`Created ${form.email}.`);
      setForm({ name: "", email: "", password: "", role: "INVESTIGATOR" });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Create failed.");
    }
  }

  async function changeRole(id, role) {
    setError("");
    try {
      await api.setUserRole(id, role);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Role change failed.");
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-400">
          ARGUS Node // Admin
        </p>
        <h1 className="text-3xl font-extrabold text-ink"><T k="users_title" /></h1>
        <p className="text-sm text-slate-500">Role changes are audit-logged.</p>
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {notice ? <p className="text-sm text-green-700">{notice}</p> : null}
      <Card title={`Operators (${users.length})`}>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Email</th>
                <th className="px-3 py-2">Role</th>
                <th className="px-3 py-2">Change role</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id} className="border-b border-slate-100">
                  <td className="px-3 py-2 font-semibold text-ink">{user.name}</td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-500">{user.email}</td>
                  <td className="px-3 py-2">{roleBadge(user.role)}</td>
                  <td className="px-3 py-2">
                    <select
                      className="rounded-xl border border-slate-300 bg-white px-2 py-1.5 text-sm"
                      value={user.role}
                      onChange={(event) => changeRole(user.id, event.target.value)}
                    >
                      {ROLES.map((role) => (
                        <option key={role} value={role}>{role}</option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="Create user" className="max-w-xl">
        <form className="grid gap-3" onSubmit={create}>
          {["name", "email", "password"].map((field) => (
            <label key={field} className="text-sm">
              <span className="font-semibold capitalize text-slate-600">{field}</span>
              <input
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 focus:border-argus-500 focus:outline-none"
                type={field === "password" ? "password" : "text"}
                value={form[field]}
                onChange={(event) => setForm({ ...form, [field]: event.target.value })}
              />
            </label>
          ))}
          <label className="text-sm">
            <span className="font-semibold text-slate-600">Role</span>
            <select
              className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2"
              value={form.role}
              onChange={(event) => setForm({ ...form, role: event.target.value })}
            >
              {ROLES.map((role) => (
                <option key={role} value={role}>{role}</option>
              ))}
            </select>
          </label>
          <button className="rounded-xl bg-argus-600 px-4 py-2 text-sm font-bold text-white hover:bg-argus-700" type="submit">
            Create operator
          </button>
        </form>
      </Card>
    </div>
  );
}
