import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, X, Shield, ShieldOff, Star, Trash2, Clock } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

const STATUS = {
  pending: { label: "In attesa", cls: "bg-amber-500/15 text-amber-600 border-amber-500/30" },
  approved: { label: "Approvato", cls: "bg-emerald-500/15 text-emerald-600 border-emerald-500/30" },
  rejected: { label: "Rifiutato", cls: "bg-red-500/15 text-red-600 border-red-500/30" },
};

export default function Admin() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const load = () => api.get("/admin/users").then((r) => setUsers(r.data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);

  const act = async (fn, ok) => { try { await fn(); toast.success(ok); load(); } catch (e) { toast.error(errMsg(e)); } };

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
          {u.can_create_events && u.role !== "admin" && <Badge variant="outline" className="rounded-full">Può creare eventi</Badge>}
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
            <Button size="icon" variant="ghost" title="Autorizza a creare eventi"
              onClick={() => act(() => api.post(`/admin/users/${u.id}/authorize/${u.can_create_events ? 0 : 1}`), "Aggiornato")}
              data-testid={`authorize-${u.id}`}><Star size={16} className={u.can_create_events ? "text-amber-500 fill-amber-500" : ""} /></Button>
            <Button size="icon" variant="ghost" title="Cambia ruolo"
              onClick={() => act(() => api.post(`/admin/users/${u.id}/role/${u.role === "admin" ? "member" : "admin"}`), "Ruolo aggiornato")}
              data-testid={`role-${u.id}`}>{u.role === "admin" ? <ShieldOff size={16} /> : <Shield size={16} />}</Button>
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
        </TabsList>
        <TabsContent value="pending" className="mt-6 space-y-3">
          {pending.length === 0 && <p className="text-muted-foreground text-center py-12 text-sm">Nessuna richiesta in attesa.</p>}
          {pending.map((u) => <Row key={u.id} u={u} />)}
        </TabsContent>
        <TabsContent value="all" className="mt-6 space-y-3">
          {others.map((u) => <Row key={u.id} u={u} />)}
        </TabsContent>
      </Tabs>
    </div>
  );
}
