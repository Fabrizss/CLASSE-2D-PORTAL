import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { CalendarCheck, BrainCircuit, MessagesSquare, Users, FileText, Droplets, Pizza, Heart, Hand, ArrowUpRight, Megaphone } from "lucide-react";
import { api, errMsg, requireOnline } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { playP2P } from "@/components/P2PLayer";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";

const ACTIONS = [
  { type: "foglietto", label: "Foglietto", icon: FileText, color: "text-amber-500" },
  { type: "secchio", label: "Secchio", icon: Droplets, color: "text-sky-500" },
  { type: "pizza", label: "Pizza", icon: Pizza, color: "text-orange-500" },
  { type: "cuore", label: "Cuore", icon: Heart, color: "text-pink-500" },
  { type: "high_five", label: "Il Cinque", icon: Hand, color: "text-primary" },
];

const stagger = { show: { transition: { staggerChildren: 0.06 } } };
const item = { hidden: { opacity: 0, y: 16 }, show: { opacity: 1, y: 0 } };

const QUOTES = [
  "Studiare stanca, ma ripetere l'anno stanca di più. 💪",
  "La 2D non molla mai… tranne il venerdì alle 13:00.",
  "Chi copia bene, in realtà ha solo studiato l'arte della velocità.",
  "Oggi è un buon giorno per fingere di aver capito la spiegazione.",
  "Ricorda: anche Einstein prendeva 4 in condotta. Probabilmente.",
  "Un foglietto lanciato oggi è un ricordo domani. 🗒️",
  "Caffè, appunti e un pizzico di panico: la ricetta della 2D.",
];

export default function Dashboard() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [events, setEvents] = useState([]);
  const [target, setTarget] = useState("");
  const [sending, setSending] = useState(false);
  const [quote] = useState(() => QUOTES[Math.floor(Math.random() * QUOTES.length)]);
  const [avvisi, setAvvisi] = useState([]);

  useEffect(() => {
    api.get("/users").then((r) => setUsers(r.data)).catch(() => {});
    api.get("/events").then((r) => setEvents(r.data)).catch(() => {});
    api.get("/avvisi").then((r) => setAvvisi(r.data)).catch(() => {});
  }, []);

  const throwIt = async (type) => {
    if (!target) return toast.error("Scegli prima un compagno");
    try { requireOnline(); } catch (err) { return toast.error(err.message); }
    setSending(true);
    playP2P(type);
    try {
      await api.post("/actions", { to_user_id: target, type });
      toast.success("Lanciato! 🎯".replace("🎯", ""));
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSending(false);
    }
  };

  const tiles = [
    { to: "/events", label: "Iscrizioni", icon: CalendarCheck, sub: `${events.length} eventi`, bg: "bg-primary text-primary-foreground border-0" },
    { to: "/study", label: "Aiuto Studio AI", icon: BrainCircuit, sub: "Interrogazioni & flashcard", bg: "" },
    { to: "/chat", label: "Canale Pubblico", icon: MessagesSquare, sub: "Chat sicura & censurata", bg: "" },
  ];

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-8">
      <motion.div variants={item}>
        <p className="text-xs tracking-[0.25em] uppercase font-bold text-muted-foreground">Dashboard</p>
        <h1 className="font-head text-4xl sm:text-5xl font-black tracking-tight mt-1">
          Ciao, {user?.name?.split(" ")[0]} <span className="text-primary">👋</span>
        </h1>
        <p className="text-muted-foreground mt-2">Ecco cosa succede nella 2D oggi.</p>
      </motion.div>

      <motion.div variants={item}>
        <Card className="p-5 flex items-center gap-4 border-primary/30 bg-primary/5">
          <div className="w-11 h-11 rounded-full bg-primary/15 text-primary grid place-items-center shrink-0 text-xl">💡</div>
          <div>
            <p className="text-xs tracking-widest uppercase font-bold text-primary">Pillola del giorno</p>
            <p className="font-head font-semibold mt-0.5">{quote}</p>
          </div>
        </Card>
      </motion.div>

      {avvisi.length > 0 && (
        <motion.div variants={item} className="space-y-3">
          {avvisi.map((a) => (
            <Card key={a.id} className="p-4 border-amber-500/40 bg-amber-500/10 flex items-start gap-3" data-testid={`avviso-${a.id}`}>
              <Megaphone size={18} className="text-amber-600 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-bold text-amber-700">Avviso da {a.from_name}</p>
                <p className="text-sm mt-0.5 whitespace-pre-wrap">{a.text}</p>
              </div>
            </Card>
          ))}
        </motion.div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {tiles.map((t) => (
          <motion.div key={t.to} variants={item}>
            <Link to={t.to} data-testid={`tile-${t.label.toLowerCase().split(" ")[0]}`}>
              <Card className={`p-6 h-full border-border transition-all hover:-translate-y-1 hover:shadow-lg cursor-pointer ${t.bg}`}>
                <div className="flex items-start justify-between">
                  <t.icon size={28} className={t.bg.includes("primary") ? "" : "text-black"} />
                  <ArrowUpRight size={20} className="opacity-50" />
                </div>
                <h3 className={`font-head text-xl font-semibold mt-6 ${t.bg.includes("primary") ? "" : "text-black"}`}>{t.label}</h3>
                <p className={`text-sm mt-1 ${t.bg.includes("primary") ? "text-primary-foreground/80" : "text-black"}`}>{t.sub}</p>
              </Card>
            </Link>
          </motion.div>
        ))}
      </div>

      <motion.div variants={item}>
        <Card className="p-6 sm:p-8 border-border">
          <div className="flex items-center gap-2 mb-1">
            <Users size={18} className="text-primary" />
            <h2 className="font-head text-2xl font-bold tracking-tight">Divertiti coi compagni</h2>
          </div>
          <p className="text-muted-foreground text-sm mb-6">
            Lancia un oggetto a un compagno: comparirà un'animazione sul tuo schermo e sul suo!
          </p>
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center">
            <Select value={target} onValueChange={setTarget}>
              <SelectTrigger className="sm:w-64 rounded-full" data-testid="p2p-target-select">
                <SelectValue placeholder="Scegli un compagno…" />
              </SelectTrigger>
              <SelectContent>
                {users.length === 0 && <SelectItem value="none" disabled>Nessun compagno ancora</SelectItem>}
                {users.map((u) => (
                  <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex flex-wrap gap-2">
              {ACTIONS.map((a) => (
                <Button key={a.type} variant="outline" disabled={sending} onClick={() => throwIt(a.type)}
                  data-testid={`throw-${a.type}-btn`}
                  className="rounded-full gap-2 active:scale-90 transition-transform hover:border-primary">
                  <a.icon size={17} className={a.color} /> {a.label}
                </Button>
              ))}
            </div>
          </div>
        </Card>
      </motion.div>
    </motion.div>
  );
}
