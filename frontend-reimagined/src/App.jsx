import { Route, Routes } from "react-router-dom";
import { AuthProvider, ProtectedRoute, RoleRoute } from "./auth/AuthContext.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Anomalies from "./pages/Anomalies.jsx";
import Atlas from "./pages/Atlas.jsx";
import Compare from "./pages/Compare.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import EntityProfile from "./pages/EntityProfile.jsx";
import Investigation from "./pages/Investigation.jsx";
import Login from "./pages/Login.jsx";
import NetworkExplorer from "./pages/NetworkExplorer.jsx";
import Users from "./pages/Users.jsx";

function Shell() {
  return (
    <div className="flex min-h-screen bg-surface font-sans text-ink">
      <Sidebar />
      <main className="min-w-0 flex-1 px-6 py-6 lg:px-10">
        <div className="mx-auto max-w-6xl">
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/network" element={<ProtectedRoute><NetworkExplorer /></ProtectedRoute>} />
            <Route path="/atlas" element={<ProtectedRoute><Atlas /></ProtectedRoute>} />
            <Route path="/compare" element={<ProtectedRoute><Compare /></ProtectedRoute>} />
            <Route path="/entities/:id" element={<ProtectedRoute><EntityProfile /></ProtectedRoute>} />
            <Route path="/anomalies" element={<ProtectedRoute><Anomalies /></ProtectedRoute>} />
            <Route path="/investigation/:id" element={<ProtectedRoute><Investigation /></ProtectedRoute>} />
            <Route
              path="/users"
              element={<RoleRoute roles={["ADMIN"]}><Users /></RoleRoute>}
            />
            <Route path="*" element={<p className="text-sm text-slate-500">Page not found.</p>} />
          </Routes>
        </div>
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
