import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { StickyNote, Plus, Trash2, Flag, Lock, Globe } from "lucide-react";
import { api, errMsg, requireOnline } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";

export default function Reminders() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [items, setItems] = useState([]);
  const [text, setText] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = () => api.get("/reminders").then((r) => setItems(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    try { requireOnline(); } catch (err) { return toast.error(err.message); }
    setSaving(true);
    try {
      const { data } = await api.post("/reminders", { text, is_public: isPublic });
      setItems((i) => [data, ...i]);
      setText(""); setIsPublic(false);
      toast.success("Reminder aggiunto");
    } catch (err) { toast.error(errMsg(err)); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    try { await api.delete(`/reminders/${id}`); setItems((i) => i.filter((x) => x.id !== id)); toast.success("Eliminato"); }
    catch (err) { toast.error(errMsg(err)); }
  };

  const report = async (id) => {
    try { await api.post(`/reminders/${id}/report`); toast.success("Segnalato all'admin"); }
    catch (err) { toast.error(errMsg(err)); }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <p className="text-xs tracking-[0.25em] uppercase font-bold text-muted-foreground flex items-center gap-1.5"><StickyNote size={14} /> Promemoria</p>
        <h1 className="font-head text-4xl font-black tracking-tight mt-1">Reminder</h1>
        <p className="text-muted-foreground mt-2 text-sm">Appunti privati o promemoria pubblici per tutta la classe.</p>
      </div>

      <Card className="p-5 border-border">
        <form onSubmit={create} className="space-y-3">
          <Textarea value={text} onChange={(e) => setText(e.target.value)} data-testid="reminder-input"
            placeholder="Es. Portare il libro di storia martedì…" className="min-h-20" maxLength={500} />
          <div className="flex items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Switch checked={isPublic} onCheckedChange={setIsPublic} data-testid="reminder-public-switch" />
              {isPublic ? <span className="flex items-center gap-1 text-primary font-medium"><Globe size={15} /> Pubblico</span>
                : <span className="flex items-center gap-1 text-muted-foreground"><Lock size={15} /> Privato</span>}
            </label>
            <Button type="submit" disabled={saving} data-testid="reminder-add-btn" className="rounded-full gap-2"><Plus size={16} /> Aggiungi</Button>
          </div>
        </form>
      </Card>

      {items.length === 0 && <p className="text-muted-foreground text-center py-12 text-sm">Nessun reminder ancora.</p>}
      <div className="space-y-3">
        {items.map((r, i) => (
          <motion.div key={r.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
            <Card className="p-4 border-border flex items-start gap-3" data-testid={`reminder-${r.id}`}>
              <div className="w-8 h-8 rounded-full grid place-items-center text-white text-xs font-bold shrink-0" style={{ background: r.avatar_color }}>
                {r.author_name?.[0]?.toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-sm">{r.mine ? "Tu" : r.author_name}</span>
                  {r.is_public
                    ? <Badge variant="outline" className="rounded-full bg-primary/10 text-primary border-primary/30"><Globe size={11} className="mr-1" /> Pubblico</Badge>
                    : <Badge variant="outline" className="rounded-full"><Lock size={11} className="mr-1" /> Privato</Badge>}
                </div>
                <p className="mt-1 whitespace-pre-wrap text-sm">{r.text}</p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {r.is_public && !r.mine && (
                  <button onClick={() => report(r.id)} data-testid={`reminder-report-${r.id}`} title="Segnala all'admin"
                    className="text-muted-foreground hover:text-amber-600 transition-colors p-1"><Flag size={16} /></button>
                )}
                {(r.mine || isAdmin) && (
                  <button onClick={() => remove(r.id)} data-testid={`reminder-del-${r.id}`} title="Elimina"
                    className="text-muted-foreground hover:text-destructive transition-colors p-1"><Trash2 size={16} /></button>
                )}
              </div>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
