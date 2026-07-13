import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=loading, false=guest, obj=auth
  const [theme, setTheme] = useState(() => localStorage.getItem("noi_theme") || "light");

  const load = useCallback(async () => {
    const t = localStorage.getItem("noi_token");
    if (!t) return setUser(false);
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch {
      localStorage.removeItem("noi_token");
      setUser(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("noi_theme", theme);
  }, [theme]);

  const login = (token, u) => { localStorage.setItem("noi_token", token); setUser(u); };
  const logout = () => { localStorage.removeItem("noi_token"); setUser(false); };
  const toggleTheme = () => setTheme((t) => (t === "dark" ? "light" : "dark"));

  return (
    <AuthCtx.Provider value={{ user, login, logout, theme, toggleTheme, reload: load }}>
      {children}
    </AuthCtx.Provider>
  );
}
