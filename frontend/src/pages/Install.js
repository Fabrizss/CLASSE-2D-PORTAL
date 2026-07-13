import { Share, PlusSquare, Bell, Smartphone, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { enablePush } from "@/lib/push";
import { useAuth } from "@/context/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const STEPS = [
  { icon: Share, title: "Apri il menu Condividi", text: "Su iPad/iPhone apri il portale in Safari e tocca l'icona Condividi (quadrato con freccia in alto)." },
  { icon: PlusSquare, title: "Aggiungi a Home", text: "Scorri e seleziona «Aggiungi a Home». Conferma: l'app NOI DI 2D apparirà come una vera app." },
  { icon: Bell, title: "Attiva le notifiche", text: "Apri l'app dalla schermata Home e tocca «Attiva notifiche» qui sotto per ricevere gli avvisi anche ad app chiusa." },
];

export default function Install() {
  const { user } = useAuth();
  const notify = async () => {
    try { await enablePush(); toast.success("Notifiche push attivate!"); }
    catch (e) { toast.error(e.message); }
  };
  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <p className="text-xs tracking-[0.25em] uppercase font-bold text-muted-foreground">Guida</p>
        <h1 className="font-head text-4xl font-black tracking-tight mt-1">Installa l'app sull'iPad</h1>
        <p className="text-muted-foreground mt-2 flex items-center gap-2"><Smartphone size={16} /> Trasforma NOI DI 2D in un'app con notifiche push.</p>
      </div>

      <div className="grid gap-4">
        {STEPS.map((s, i) => (
          <Card key={i} className="p-6 border-border flex gap-4 items-start hover:-translate-y-0.5 hover:shadow-lg transition-all">
            <div className="w-11 h-11 rounded-full bg-primary/10 text-primary grid place-items-center shrink-0 font-head font-bold">{i + 1}</div>
            <div className="flex-1">
              <div className="flex items-center gap-2"><s.icon size={18} className="text-primary" /><h3 className="font-head font-semibold text-lg">{s.title}</h3></div>
              <p className="text-muted-foreground text-sm mt-1.5">{s.text}</p>
            </div>
          </Card>
        ))}
      </div>

      <Button onClick={notify} data-testid="install-enable-push" className="rounded-full gap-2 h-11 w-full sm:w-auto">
        <Bell size={17} /> Attiva notifiche su questo dispositivo
      </Button>

      {user?.role === "admin" && (
        <Card className="p-6 border-primary/30 bg-primary/5">
          <div className="flex items-center gap-2 mb-2"><ShieldCheck size={18} className="text-primary" /><h3 className="font-head font-semibold text-lg">Come creare il primo admin</h3></div>
          <p className="text-muted-foreground text-sm">
            Il primo account admin viene creato automaticamente all'avvio con le credenziali definite nel file <code className="text-primary">backend/.env</code> (<code>ADMIN_EMAIL</code> e <code>ADMIN_PASSWORD</code>).
            Accedi con quelle credenziali, poi da questo Pannello Admin puoi approvare i nuovi membri e promuovere altri utenti ad admin.
          </p>
        </Card>
      )}
    </div>
  );
}
