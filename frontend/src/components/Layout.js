import { useState, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { LayoutDashboard, CalendarCheck, BrainCircuit, MessagesSquare, Newspaper, StickyNote, Shield, Download, Sun, Moon, LogOut, Menu, X, WifiOff, Mail } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useBranding } from "@/context/BrandingContext";
import { useOnline } from "@/hooks/useOnline";
import { api } from "@/lib/api";
import { isStaff } from "@/lib/roles";
import { LOGO } from "@/App";
import P2PLayer from "@/components/P2PLayer";
import { Button } from "@/components/ui/button";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/events", label: "Iscrizioni", icon: CalendarCheck },
  { to: "/study", label: "Aiuto Studio", icon: BrainCircuit },
  { to: "/news", label: "News", icon: Newspaper },
  { to: "/reminders", label: "Reminder", icon: StickyNote },
  { to: "/messaggi", label: "Messaggi", icon: Mail },
  { to: "/chat", label: "Canale", icon: MessagesSquare },
  { to: "/install", label: "Installa App", icon: Download },
];

export function Logo({ size = 34 }) {
  const { logoUrl } = useBranding();
  return <img src={logoUrl || LOGO} alt="NOI DI 2D" width={size} height={size}
    className="rounded-full object-cover shadow-sm ring-1 ring-primary/20" style={{ width: size, height: size }} />;
}

export default function Layout({ children }) {
  const { user, logout, theme, toggleTheme } = useAuth();
  const loc = useLocation();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const online = useOnline();
  const links = isStaff(user?.role) ? [...NAV, { to: "/admin", label: "Admin", icon: Shield }] : NAV;

  // Cache-warming: quando online, precarica i dati read-only per la modalità offline (via service worker)
  useEffect(() => {
    if (!online) return;
    ["/chat/messages", "/news", "/events"].forEach((p) => api.get(p).catch(() => {}));
  }, [online, loc.pathname]);

  const NavLinks = ({ onClick }) => (
    <>
      {links.map(({ to, label, icon: Icon }) => {
        const active = loc.pathname === to;
        return (
          <Link key={to} to={to} onClick={onClick} data-testid={`nav-${label.toLowerCase().replace(/\s/g, "-")}`}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-full text-sm font-semibold transition-colors ${
              active ? "bg-primary text-primary-foreground shadow-md shadow-primary/20"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary"}`}>
            <Icon size={17} /> {label}
          </Link>
        );
      })}
    </>
  );

  return (
    <div className="App min-h-screen bg-background noise-overlay relative">
      <div className="blob" style={{ background: "#a855f7", width: 480, height: 480, top: -120, right: -120 }} />
      <div className="blob" style={{ background: "#f472b6", width: 420, height: 420, bottom: -160, left: -140 }} />
      <div className="blob" style={{ background: "#7C3AED", width: 360, height: 360, top: "40%", left: "55%" }} />
      <P2PLayer />
      <header className="sticky top-0 z-50 glass-strong border-b border-border/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2.5">
            <Logo />
            <span className="font-head font-extrabold tracking-tight text-lg leading-none">
              NOI DI <span className="text-primary">2D</span>
            </span>
          </Link>
          <nav className="hidden lg:flex items-center gap-1">
            <NavLinks />
          </nav>
          <div className="flex items-center gap-2">
            <button onClick={toggleTheme} data-testid="theme-toggle"
              className="p-2 rounded-full hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors">
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <div className="hidden sm:flex items-center gap-2 pl-1">
              <div className="w-8 h-8 rounded-full grid place-items-center text-white text-xs font-bold"
                style={{ background: user?.avatar_color }}>
                {user?.name?.[0]?.toUpperCase()}
              </div>
              <button onClick={() => { logout(); nav("/auth"); }} data-testid="logout-btn"
                className="p-2 rounded-full hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors">
                <LogOut size={18} />
              </button>
            </div>
            <button className="lg:hidden p-2 rounded-full hover:bg-secondary" data-testid="mobile-menu-btn"
              onClick={() => setOpen((o) => !o)}>
              {open ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
        <AnimatePresence>
          {open && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
              className="lg:hidden overflow-hidden border-t border-border glass">
              <div className="p-4 flex flex-col gap-2">
                <NavLinks onClick={() => setOpen(false)} />
                <Button variant="ghost" onClick={() => { logout(); nav("/auth"); }} className="justify-start text-destructive">
                  <LogOut size={17} className="mr-2" /> Esci
                </Button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </header>
      <AnimatePresence>
        {!online && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            data-testid="offline-banner"
            className="sticky top-16 z-40 bg-amber-500/95 text-amber-950 overflow-hidden">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-2 flex items-center gap-2 text-sm font-semibold">
              <WifiOff size={16} /> Sei offline — stai vedendo i dati salvati in sola lettura. Le azioni sono disabilitate.
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8 relative z-10">{children}</main>
    </div>
  );
}
