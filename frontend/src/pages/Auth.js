import { useState } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { LOGO } from "@/App";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Sparkles } from "lucide-react";

export default function Auth() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [tab, setTab] = useState("login");
  const [loading, setLoading] = useState(false);
  const [f, setF] = useState({ name: "", email: "", password: "" });
  const on = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (tab === "login") {
        const { data } = await api.post("/auth/login", { email: f.email, password: f.password });
        login(data.token, data.user);
        toast.success(`Bentornato, ${data.user.name}!`);
        nav("/");
      } else {
        await api.post("/auth/register", f);
        toast.success("Registrazione inviata! Attendi l'approvazione di un admin.");
        setTab("login");
      }
    } catch (err) {
      toast.error(errMsg(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-background">
      <div className="hidden lg:flex flex-col justify-between p-12 bg-primary text-primary-foreground relative overflow-hidden">
        <div className="absolute -top-24 -right-24 w-96 h-96 rounded-full bg-white/10 blur-2xl" />
        <div className="absolute bottom-10 -left-20 w-80 h-80 rounded-full bg-fuchsia-400/20 blur-3xl" />
        <div className="flex items-center gap-3 relative z-10">
          <img src={LOGO} alt="logo" className="w-11 h-11 rounded-full ring-2 ring-white/30" />
          <span className="font-head font-extrabold text-xl">NOI DI 2D</span>
        </div>
        <div className="relative z-10">
          <h1 className="font-head text-5xl font-black leading-[1.05] tracking-tight">
            Il portale della classe.<br />Fatto dai compagni,<br />per i compagni.
          </h1>
          <p className="mt-6 text-primary-foreground/80 text-lg max-w-md">
            Iscrizioni agli eventi, aiuto studio con l'AI, canale sicuro e un pizzico di divertimento tra banchi.
          </p>
        </div>
        <div className="relative z-10 flex items-center gap-2 text-sm text-primary-foreground/70">
          <Sparkles size={16} /> Una scuola competitiva merita strumenti migliori.
        </div>
      </div>

      <div className="flex items-center justify-center p-6 sm:p-12">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-sm">
          <div className="lg:hidden flex items-center gap-2.5 mb-8">
            <img src={LOGO} alt="logo" className="w-10 h-10 rounded-full ring-1 ring-primary/20" />
            <span className="font-head font-extrabold text-lg">NOI DI <span className="text-primary">2D</span></span>
          </div>
          <h2 className="font-head text-3xl font-bold tracking-tight">
            {tab === "login" ? "Accedi" : "Crea account"}
          </h2>
          <p className="text-muted-foreground mt-1 mb-6 text-sm">
            {tab === "login" ? "Bentornato nel portale della 2D." : "Registrati, poi un admin ti approverà."}
          </p>

          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="grid grid-cols-2 w-full mb-6">
              <TabsTrigger value="login" data-testid="tab-login">Accedi</TabsTrigger>
              <TabsTrigger value="register" data-testid="tab-register">Registrati</TabsTrigger>
            </TabsList>
            <form onSubmit={submit} className="space-y-4">
              <TabsContent value="register" className="m-0 space-y-4">
                <div>
                  <Label htmlFor="name">Nome</Label>
                  <Input id="name" data-testid="input-name" value={f.name} onChange={on("name")}
                    required={tab === "register"} placeholder="Mario Rossi" className="mt-1.5" />
                </div>
              </TabsContent>
              <div>
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" data-testid="input-email" value={f.email} onChange={on("email")}
                  required placeholder="tu@scuola.it" className="mt-1.5" />
              </div>
              <div>
                <Label htmlFor="password">Password</Label>
                <Input id="password" type="password" data-testid="input-password" value={f.password} onChange={on("password")}
                  required placeholder="••••••••" className="mt-1.5" />
              </div>
              <Button type="submit" disabled={loading} data-testid="auth-submit-btn"
                className="w-full rounded-full h-11 font-semibold active:scale-95 transition-transform">
                {loading ? "Attendere…" : tab === "login" ? "Entra" : "Registrati"}
              </Button>
            </form>
          </Tabs>
        </motion.div>
      </div>
    </div>
  );
}
