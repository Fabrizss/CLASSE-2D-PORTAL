import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import Auth from "@/pages/Auth";
import Dashboard from "@/pages/Dashboard";
import Events from "@/pages/Events";
import Study from "@/pages/Study";
import Chat from "@/pages/Chat";
import News from "@/pages/News";
import Reminders from "@/pages/Reminders";
import Admin from "@/pages/Admin";
import Install from "@/pages/Install";

export const LOGO = "https://customer-assets.emergentagent.com/job_fd8a2fce-eb5b-4ab8-a990-d9b853fdd702/artifacts/oxjy3e6l_Gemini_Generated_Image_.png";

function Loader() {
  return (
    <div className="min-h-screen grid place-items-center bg-background">
      <div className="animate-pulse text-muted-foreground font-head tracking-widest text-sm">NOI DI 2D…</div>
    </div>
  );
}

function Protected({ children, adminOnly }) {
  const { user } = useAuth();
  if (user === null) return <Loader />;
  if (!user) return <Navigate to="/auth" replace />;
  if (adminOnly && user.role !== "admin") return <Navigate to="/" replace />;
  return <Layout>{children}</Layout>;
}

function Shell() {
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/auth" element={user ? <Navigate to="/" replace /> : <Auth />} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/events" element={<Protected><Events /></Protected>} />
      <Route path="/study" element={<Protected><Study /></Protected>} />
      <Route path="/chat" element={<Protected><Chat /></Protected>} />
      <Route path="/news" element={<Protected><News /></Protected>} />
      <Route path="/reminders" element={<Protected><Reminders /></Protected>} />
      <Route path="/install" element={<Protected><Install /></Protected>} />
      <Route path="/admin" element={<Protected adminOnly><Admin /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Shell />
        <Toaster position="top-center" richColors />
      </BrowserRouter>
    </AuthProvider>
  );
}
