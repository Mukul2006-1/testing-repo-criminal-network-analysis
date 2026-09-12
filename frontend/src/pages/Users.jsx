import { useEffect, useState } from "react";
import { ApiError, api } from "../services/api.js";

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
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-gray-900">User administration</h1>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {notice ? <p className="text-sm text-green-700">{notice}</p> : null}
      <div className="overflow-x-auto rounded border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b bg-gray-50">
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Email</th>
              <th className="px-3 py-2">Role</th>
              <th className="px-3 py-2">Change role</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id} className="border-b">
                <td className="px-3 py-2">{user.name}</td>
                <td className="px-3 py-2 font-mono text-xs">{user.email}</td>
                <td className="px-3 py-2">{user.role}</td>
                <td className="px-3 py-2">
                  <select
                    className="rounded border border-gray-300 px-2 py-1"
                    value={user.role}
                    onChange={(event) => changeRole(user.id, event.target.value)}
                  >
                    {["INVESTIGATOR", "SENIOR_INVESTIGATOR", "ADMIN"].map((role) => (
                      <option key={role} value={role}>{role}</option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form className="grid max-w-lg gap-3 rounded border border-gray-200 bg-white p-4 shadow-sm" onSubmit={create}>
        <h2 className="font-medium text-gray-900">Create user</h2>
        {["name", "email", "password"].map((field) => (
          <label key={field} className="text-sm">
            <span className="capitalize text-gray-600">{field}</span>
            <input
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
              type={field === "password" ? "password" : "text"}
              value={form[field]}
              onChange={(event) => setForm({ ...form, [field]: event.target.value })}
            />
          </label>
        ))}
        <label className="text-sm">
          <span className="text-gray-600">Role</span>
          <select
            className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
            value={form.role}
            onChange={(event) => setForm({ ...form, role: event.target.value })}
          >
            {["INVESTIGATOR", "SENIOR_INVESTIGATOR", "ADMIN"].map((role) => (
              <option key={role} value={role}>{role}</option>
            ))}
          </select>
        </label>
        <button className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white" type="submit">
          Create
        </button>
      </form>
    </div>
  );
}
