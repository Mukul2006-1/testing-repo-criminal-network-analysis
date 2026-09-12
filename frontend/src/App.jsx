import { Link, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { AuthProvider, ProtectedRoute, RoleRoute, useAuth } from "./auth/AuthContext.jsx";
import Anomalies from "./pages/Anomalies.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import EntityProfile from "./pages/EntityProfile.jsx";
import Investigation from "./pages/Investigation.jsx";
import Login from "./pages/Login.jsx";
import NetworkExplorer from "./pages/NetworkExplorer.jsx";
import Users from "./pages/Users.jsx";

function linkClass({ isActive }) {
  return `rounded px-3 py-1.5 text-sm ${isActive ? "bg-blue-700 text-white" : "text-gray-700 hover:bg-gray-100"}`;
}

function Shell() {
  const { user, logout, isAdmin } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="no-print border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-3">
          <Link to="/" className="mr-2 font-semibold">
            Crime Network Intelligence
          </Link>
          {user ? (
            <>
              <nav className="flex flex-wrap gap-1">
                <NavLink to="/" end className={linkClass}>Dashboard</NavLink>
                <NavLink to="/network" className={linkClass}>Network</NavLink>
                <NavLink to="/anomalies" className={linkClass}>Anomalies</NavLink>
                {isAdmin ? <NavLink to="/users" className={linkClass}>Users</NavLink> : null}
              </nav>
              <span className="ml-auto text-xs text-gray-500">
                {user.email} · {user.role}
              </span>
              <button
                className="rounded border border-gray-300 px-3 py-1.5 text-sm"
                type="button"
                onClick={() => {
                  logout();
                  navigate("/login");
                }}
              >
                Logout
              </button>
            </>
          ) : null}
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/network" element={<ProtectedRoute><NetworkExplorer /></ProtectedRoute>} />
          <Route path="/entities/:id" element={<ProtectedRoute><EntityProfile /></ProtectedRoute>} />
          <Route path="/anomalies" element={<ProtectedRoute><Anomalies /></ProtectedRoute>} />
          <Route path="/investigation/:id" element={<ProtectedRoute><Investigation /></ProtectedRoute>} />
          <Route
            path="/users"
            element={<RoleRoute roles={["ADMIN"]}><Users /></RoleRoute>}
          />
          <Route path="*" element={<p className="text-sm text-gray-500">Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}
