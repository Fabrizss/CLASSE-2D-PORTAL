import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, X, Star, Trash2, Clock, Ban, Unlock, MessageSquare, BookOpen, CalendarClock } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { GuideSistemi } from "@/components/GuideSistemi";
import { OrarioAdmin } from "@/components/OrarioAdmin";

const STATUS = {
  pending: { label: "In attesa", cls: "bg-amber-500/15 text-amber-600 border-amber-500/30" },
  approved: { label: "Approvato", cls: "bg-emerald-500/15 text-emerald-600 border-emerald-500/30" },
  rejected: { label: "Rifiutato", cls: "bg-red-500/15 text-red-600 border-red-500/30" },
};

export default function Admin() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [banTarget, setBanTarget] = useState(null);
  const [avvisoTarget, setAvvisoTarget] = useState(null);
  const [avvisoText, setAvvisoText] = useState("");
  const load = () => api.get("/admin/users").then((r) => setUsers(r.data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);

  const act = async (fn, ok) => { try { await fn(); toast.success(ok); load(); } catch (e) { toast.error(errMsg(e)); } };

  const sendAvviso = async () => {
    if (!avvisoText.trim()) return;
    try { await api.post("/admin/avvisi", { user_id: avvisoTarget.id, text: avvisoText }); toast.success("Avviso inviato"); setAvvisoTarget(null); setAvvisoText(""); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const doBan = (mode, hours) => act(() => api.post(`/admin/users/${banTarget.id}/ban`, { mode, hours }), "Utente sospeso").then(() => setBanTarget(null));

  const isBanned = (u) => u.ban_permanent || (u.banned_until && u.banned_until > new Date().toISOString());
  const ROLE_LABEL = { admin: "Admin", professore: "Professore", member: "Studente" };

  const pending = users.filter((u) => u.status === "pending");
  const others = users.filter((u) => u.status !== "pending");

  const Row = ({ u }) => (
    <div className="flex items-center gap-3 p-4 rounded-xl border border-border hover:bg-secondary/40 transition-colors" data-testid={`admin-user-${u.id}`}>
      <div className="w-9 h-9 rounded-full grid place-items-center text-white text-sm font-bold shrink-0" style={{ background: u.avatar_color }}>
        {u.name?.[0]?.toUpperCase()}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold truncate">{u.name}</span>
          {u.role === "admin" && <Badge variant="outline" className="rounded-full bg-primary/15 text-primary border-primary/30">Admin</Badge>}
          {u.role === "professore" && <Badge variant="outline" className="rounded-full bg-sky-500/15 text-sky-600 border-sky-500/30">Professore</Badge>}
          {u.can_create_events && u.role === "member" && <Badge variant="outline" className="rounded-full">Può creare eventi</Badge>}
          {isBanned(u) && <Badge variant="outline" className="rounded-full bg-red-500/15 text-red-600 border-red-500/30">{u.ban_permanent ? "Bannato" : "Sospeso"}</Badge>}
          <Badge variant="outline" className={`rounded-full ${STATUS[u.status]?.cls}`}>{STATUS[u.status]?.label}</Badge>
        </div>
        <span className="text-xs text-muted-foreground truncate">{u.email}</span>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        {u.status === "pending" ? (
          <>
            <Button size="sm" onClick={() => act(() => api.post(`/admin/users/${u.id}/approve`), "Approvato")} data-testid={`approve-${u.id}`} className="rounded-full gap-1"><Check size={14} /> Approva</Button>
            <Button size="sm" variant="outline" onClick={() => act(() => api.post(`/admin/users/${u.id}/reject`), "Rifiutato")} data-testid={`reject-${u.id}`} className="rounded-full"><X size={14} /></Button>
          </>
        ) : u.id !== user.id && (
          <>
            <Button size="icon" variant="ghost" title="Avviso privato"
              onClick={() => setAvvisoTarget(u)} data-testid={`avviso-${u.id}`}><MessageSquare size={16} className="text-primary" /></Button>
            <Button size="icon" variant="ghost" title="Autorizza a creare eventi"
              onClick={() => act(() => api.post(`/admin/users/${u.id}/authorize/${u.can_create_events ? 0 : 1}`), "Aggiornato")}
              data-testid={`authorize-${u.id}`}><Star size={16} className={u.can_create_events ? "text-amber-500 fill-amber-500" : ""} /></Button>
            <Select value={u.role} onValueChange={(role) => act(() => api.post(`/admin/users/${u.id}/role/${role}`), "Ruolo aggiornato")}>
              <SelectTrigger className="h-9 w-[125px] rounded-full text-xs gap-1" data-testid={`role-${u.id}`}>
                <SelectValue>{ROLE_LABEL[u.role]}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="admin">Admin</SelectItem>
                <SelectItem value="professore">Professore</SelectItem>
                <SelectItem value="member">Studente</SelectItem>
              </SelectContent>
            </Select>
            {isBanned(u) ? (
              <Button size="icon" variant="ghost" title="Rimuovi ban"
                onClick={() => act(() => api.post(`/admin/users/${u.id}/unban`), "Ban rimosso")}
                data-testid={`unban-${u.id}`}><Unlock size={16} className="text-emerald-500" /></Button>
            ) : (
              <Button size="icon" variant="ghost" title="Banna"
                onClick={() => setBanTarget(u)} data-testid={`ban-${u.id}`}><Ban size={16} className="text-amber-600" /></Button>
            )}
            <Button size="icon" variant="ghost" title="Elimina"
              onClick={() => act(() => api.delete(`/admin/users/${u.id}`), "Eliminato")}
              data-testid={`delete-${u.id}`}><Trash2 size={16} className="text-destructive" /></Button>
          </>
        )}
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs tracking-[0.25em] uppercase font-bold text-muted-foreground">Gestione</p>
        <h1 className="font-head text-4xl font-black tracking-tight mt-1">Pannello Admin</h1>
      </div>
      <Tabs defaultValue="pending">
        <TabsList>
          <TabsTrigger value="pending" data-testid="tab-pending" className="gap-2">
            <Clock size={15} /> In attesa {pending.length > 0 && <span className="ml-1 bg-primary text-primary-foreground rounded-full px-1.5 text-xs">{pending.length}</span>}
          </TabsTrigger>
          <TabsTrigger value="all" data-testid="tab-all">Tutti i membri</TabsTrigger>
          <TabsTrigger value="orario" data-testid="tab-orario" className="gap-2"><CalendarClock size={15} /> Orario</TabsTrigger>
          <TabsTrigger value="guide" data-testid="tab-guide" className="gap-2"><BookOpen size={15} /> Guide e Sistemi</TabsTrigger>
        </TabsList>
        <TabsContent value="pending" className="mt-6 space-y-3">
          {pending.length === 0 && <p className="text-muted-foreground text-center py-12 text-sm">Nessuna richiesta in attesa.</p>}
          {pending.map((u) => <Row key={u.id} u={u} />)}
        </TabsContent>
        <TabsContent value="all" className="mt-6 space-y-3">
          {others.map((u) => <Row key={u.id} u={u} />)}
        </TabsContent>
        <TabsContent value="orario" className="mt-6">
          <OrarioAdmin />
        </TabsContent>
        <TabsContent value="guide" className="mt-6">
          <GuideSistemi />
        </TabsContent>
      </Tabs>

      <Dialog open={!!banTarget} onOpenChange={(o) => !o && setBanTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle className="font-head">Sospendi {banTarget?.name}</DialogTitle>
            <DialogDescription>Scegli la durata: l'utente non potrà accedere finché è sospeso.</DialogDescription>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">Scegli la durata della sospensione. L'utente non potrà accedere.</p>
          <div className="grid gap-2 mt-2">
            <Button variant="outline" className="rounded-full justify-start" onClick={() => doBan("temp", 24)} data-testid="ban-24h">Temporaneo · 24 ore</Button>
            <Button variant="outline" className="rounded-full justify-start" onClick={() => doBan("temp", 168)} data-testid="ban-7d">Temporaneo · 7 giorni</Button>
            <Button variant="destructive" className="rounded-full justify-start" onClick={() => doBan("perm", 0)} data-testid="ban-perm">Permanente</Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!avvisoTarget} onOpenChange={(o) => { if (!o) { setAvvisoTarget(null); setAvvisoText(""); } }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="font-head">Avviso privato a {avvisoTarget?.name}</DialogTitle>
            <DialogDescription>Riceverà l'avviso in dashboard e una notifica push.</DialogDescription>
          </DialogHeader>
          <Textarea value={avvisoText} onChange={(e) => setAvvisoText(e.target.value)} data-testid="avviso-text"
            placeholder="Scrivi l'avviso…" className="min-h-24" maxLength={500} />
          <Button onClick={sendAvviso} data-testid="avviso-send" className="rounded-full w-full mt-2">Invia avviso</Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
