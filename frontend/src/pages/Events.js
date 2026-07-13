import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { Plus, MapPin, Clock, Users, Trash2, Bell, Check } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { enablePush } from "@/lib/push";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";

const BANNER = "https://images.pexels.com/photos/20059728/pexels-photo-20059728.jpeg";
const URGENCY = {
  bassa: { label: "Bassa", cls: "bg-slate-500/15 text-slate-600 dark:text-slate-300 border-slate-500/30" },
  normale: { label: "Normale", cls: "bg-primary/15 text-primary border-primary/30" },
  alta: { label: "Alta", cls: "bg-amber-500/15 text-amber-600 border-amber-500/30" },
  urgente: { label: "Urgente", cls: "bg-red-500/15 text-red-600 border-red-500/30" },
};

export default function Events() {
  const { user } = useAuth();
  const canCreate = user?.role === "admin" || user?.can_create_events;
  const [events, setEvents] = useState([]);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", urgency: "normale", deadline: "", location: "" });

  const load = () => api.get("/events").then((r) => setEvents(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/events", form);
      toast.success("Iscrizione pubblicata! Notifiche ed email inviate.");
      setOpen(false);
      setForm({ title: "", description: "", urgency: "normale", deadline: "", location: "" });
      load();
    } catch (err) {
      toast.error(errMsg(err));
    } finally { setSaving(false); }
  };

  const signup = async (id) => {
    try {
      const { data } = await api.post(`/events/${id}/signup`);
      setEvents((ev) => ev.map((e) => e.id === id ? { ...e, signed_up: data.signed_up, signup_count: data.signup_count } : e));
      toast.success(data.signed_up ? "Iscritto!" : "Iscrizione annullata");
    } catch (err) { toast.error(errMsg(err)); }
  };

  const remove = async (id) => {
    try { await api.delete(`/events/${id}`); setEvents((ev) => ev.filter((e) => e.id !== id)); toast.success("Eliminata"); }
    catch (err) { toast.error(errMsg(err)); }
  };

  const notify = async () => {
    try { await enablePush(); toast.success("Notifiche push attivate su questo dispositivo!"); }
    catch (e) { toast.error(e.message); }
  };

  return (
    <div className="space-y-8">
      <div className="relative rounded-3xl overflow-hidden h-52 sm:h-64">
        <img src={BANNER} alt="Auditorium eventi scuola" className="w-full h-full object-cover" />
        <div className="absolute inset-0 bg-primary/60 mix-blend-multiply" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 to-transparent" />
        <div className="absolute bottom-0 p-6 sm:p-8 text-white">
          <p className="text-xs tracking-[0.25em] uppercase font-bold opacity-80">Eventi & Gare</p>
          <h1 className="font-head text-3xl sm:text-4xl font-black tracking-tight">Iscrizioni</h1>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="outline" onClick={notify} data-testid="enable-push-btn" className="rounded-full gap-2">
          <Bell size={16} /> Attiva notifiche
        </Button>
        {canCreate && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button data-testid="new-event-btn" className="rounded-full gap-2 active:scale-95 transition-transform">
                <Plus size={18} /> Nuova iscrizione
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
              <DialogHeader><DialogTitle className="font-head">Richiedi un'iscrizione</DialogTitle></DialogHeader>
              <form onSubmit={create} className="space-y-4">
                <div><Label>Titolo</Label><Input required value={form.title} data-testid="event-title-input"
                  onChange={(e) => setForm({ ...form, title: e.target.value })} className="mt-1.5" placeholder="Olimpiadi di Matematica" /></div>
                <div><Label>Descrizione</Label><Textarea required value={form.description} data-testid="event-desc-input"
                  onChange={(e) => setForm({ ...form, description: e.target.value })} className="mt-1.5" placeholder="Dettagli dell'evento…" /></div>
                <div className="grid grid-cols-2 gap-3">
                  <div><Label>Urgenza</Label>
                    <Select value={form.urgency} onValueChange={(v) => setForm({ ...form, urgency: v })}>
                      <SelectTrigger className="mt-1.5" data-testid="event-urgency-select"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {Object.entries(URGENCY).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div><Label>Scadenza</Label><Input value={form.deadline} data-testid="event-deadline-input"
                    onChange={(e) => setForm({ ...form, deadline: e.target.value })} className="mt-1.5" placeholder="12 Giu" /></div>
                </div>
                <div><Label>Luogo</Label><Input value={form.location} data-testid="event-location-input"
                  onChange={(e) => setForm({ ...form, location: e.target.value })} className="mt-1.5" placeholder="Aula Magna" /></div>
                <DialogFooter>
                  <Button type="submit" disabled={saving} data-testid="submit-event-btn" className="rounded-full w-full">
                    {saving ? "Invio…" : "Pubblica & Notifica"}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        )}
      </div>

      {events.length === 0 && <p className="text-muted-foreground text-center py-16">Nessuna iscrizione al momento.</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {events.map((e, i) => {
          const u = URGENCY[e.urgency] || URGENCY.normale;
          return (
            <motion.div key={e.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <Card className="p-6 border-border h-full flex flex-col hover:-translate-y-1 hover:shadow-lg transition-all">
                <div className="flex items-start justify-between gap-3">
                  <Badge variant="outline" className={`rounded-full ${u.cls}`}>{u.label}</Badge>
                  {(user?.role === "admin" || e.created_by === user?.id) && (
                    <button onClick={() => remove(e.id)} data-testid={`delete-event-${e.id}`}
                      className="text-muted-foreground hover:text-destructive transition-colors"><Trash2 size={16} /></button>
                  )}
                </div>
                <h3 className="font-head text-xl font-semibold mt-3">{e.title}</h3>
                <p className="text-muted-foreground text-sm mt-2 flex-1">{e.description}</p>
                <div className="flex flex-wrap gap-4 text-xs text-muted-foreground mt-4">
                  {e.deadline && <span className="flex items-center gap-1"><Clock size={13} /> {e.deadline}</span>}
                  {e.location && <span className="flex items-center gap-1"><MapPin size={13} /> {e.location}</span>}
                  <span className="flex items-center gap-1"><Users size={13} /> {e.signup_count} iscritti</span>
                </div>
                <Button onClick={() => signup(e.id)} data-testid={`signup-btn-${e.id}`}
                  variant={e.signed_up ? "secondary" : "default"}
                  className="rounded-full mt-5 gap-2 active:scale-95 transition-transform">
                  {e.signed_up ? <><Check size={16} /> Iscritto</> : "Iscriviti"}
                </Button>
              </Card>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
