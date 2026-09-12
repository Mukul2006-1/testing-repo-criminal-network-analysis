import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, clearToken, getToken, onUnauthorized, setToken } from "../services/api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(true);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    api.logout().catch(() => {});
  }, []);

  useEffect(() => {
    onUnauthorized(() => {
      clearToken();
      setUser(null);
    });
  }, []);

  const login = useCallback(async (username, password) => {
    const data = await api.login(username, password);
    setToken(data.access_token);
    setUser(data.user);
    return data.user;
  }, []);

  const value = useMemo(
    () => ({ user, token: getToken(), login, logout, authChecked, isAdmin: user?.role === "ADMIN" }),
    [user, login, logout, authChecked]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

export function ProtectedRoute({ children }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}

export function RoleRoute({ roles, children }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (!roles.includes(user.role)) {
    return (
      <main className="p-8">
        <h1 className="text-xl font-semibold">Forbidden</h1>
        <p className="mt-2 text-gray-600">Your role cannot access this page.</p>
      </main>
    );
  }
  return children;
}
