import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);
const USER_CACHE_KEY = "noi_user_cache";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=loading, false=guest, obj=auth
  const [theme, setTheme] = useState(() => localStorage.getItem("noi_theme") || "light");

  const load = useCallback(async () => {
    const t = localStorage.getItem("noi_token");
    if (!t) return setUser(false);
    const cached = localStorage.getItem(USER_CACHE_KEY);
    if (!navigator.onLine && cached) {
      // Offline: mostra subito l'ultimo utente noto invece di sloggare per un errore di rete.
      return setUser(JSON.parse(cached));
    }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      localStorage.setItem(USER_CACHE_KEY, JSON.stringify(data));
    } catch (err) {
      if (err.response && [401, 403].includes(err.response.status)) {
        // Token davvero non valido/scaduto: sloggiamo per sicurezza.
        localStorage.removeItem("noi_token");
        localStorage.removeItem(USER_CACHE_KEY);
        setUser(false);
      } else if (cached) {
        // Errore di rete (offline/timeout): resta collegato con l'ultimo backup noto.
        setUser(JSON.parse(cached));
      } else {
        setUser(false);
      }
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("noi_theme", theme);
  }, [theme]);

  const login = (token, u) => {
    localStorage.setItem("noi_token", token);
    localStorage.setItem(USER_CACHE_KEY, JSON.stringify(u));
    setUser(u);
  };
  const logout = () => {
    localStorage.removeItem("noi_token");
    localStorage.removeItem(USER_CACHE_KEY);
    setUser(false);
  };
  const toggleTheme = () => setTheme((t) => (t === "dark" ? "light" : "dark"));

  return (
    <AuthCtx.Provider value={{ user, login, logout, theme, toggleTheme, reload: load }}>
      {children}
    </AuthCtx.Provider>
  );
}
