import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarClock, Save, CheckCircle2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

const TYPE_LABEL = { provvisorio: "Provvisorio", settimana: "Settimana specifica", definitivo: "Definitivo" };

export function OrarioAdmin() {
  const [data, setData] = useState(null);
  const [grids, setGrids] = useState({});
  const [labels, setLabels] = useState({});
  const [saving, setSaving] = useState(false);

  const load = () => api.get("/admin/orario").then((r) => {
    setData(r.data);
    const g = {}; const l = {};
    Object.entries(r.data.grids).forEach(([t, v]) => { g[t] = v.grid || {}; l[t] = v.week_label || ""; });
    setGrids(g); setLabels(l);
  }).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);

  const setCell = (type, day, hour, value) => {
    setGrids((g) => ({ ...g, [type]: { ...g[type], [`${day}-${hour}`]: value } }));
  };

  const save = async (type) => {
    setSaving(true);
    try {
      await api.post("/admin/orario", { type, grid: grids[type] || {}, week_label: labels[type] || null });
      toast.success(`Orario "${TYPE_LABEL[type]}" salvato`);
    } catch (e) { toast.error(errMsg(e)); }
    finally { setSaving(false); }
  };

  const setActive = async (type) => {
    try { await api.post("/admin/orario/active", { type }); toast.success(`Orario attivo: ${TYPE_LABEL[type]}`); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!data) return <p className="text-muted-foreground text-center py-10 text-sm">Caricamento orario…</p>;

  return (
    <Card className="p-6 border-border" data-testid="orario-admin-section">
      <div className="flex items-center gap-2 mb-1">
        <CalendarClock size={18} className="text-primary" />
        <h3 className="font-head text-lg font-semibold">Gestione Orario</h3>
      </div>
      <p className="text-xs text-muted-foreground mb-4">Modifica le tre versioni dell'orario e scegli quale mostrare a tutti nella Dashboard.</p>
      <Tabs defaultValue="definitivo">
        <TabsList>
          {Object.keys(TYPE_LABEL).map((t) => (
            <TabsTrigger key={t} value={t} data-testid={`orario-tab-${t}`} className="gap-1.5">
              {TYPE_LABEL[t]} {data.active_type === t && <CheckCircle2 size={13} className="text-emerald-500" />}
            </TabsTrigger>
          ))}
        </TabsList>
        {Object.keys(TYPE_LABEL).map((t) => (
          <TabsContent key={t} value={t} className="mt-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              {t === "settimana" ? (
                <Input value={labels[t] || ""} onChange={(e) => setLabels((l) => ({ ...l, [t]: e.target.value }))}
                  data-testid="orario-week-label-input" placeholder="Es. Settimana dal 12 al 16 Ottobre" className="max-w-xs" />
              ) : <div />}
              <div className="flex gap-2">
                {data.active_type === t ? (
                  <Badge variant="outline" className="rounded-full bg-emerald-500/15 text-emerald-600 border-emerald-500/30">Attivo ora</Badge>
                ) : (
                  <Button size="sm" variant="outline" onClick={() => setActive(t)} data-testid={`orario-set-active-${t}`} className="rounded-full">Imposta come attivo</Button>
                )}
                <Button size="sm" onClick={() => save(t)} disabled={saving} data-testid={`orario-save-${t}`} className="rounded-full gap-1.5"><Save size={14} /> Salva</Button>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr>
                    <th className="p-2 text-left text-xs text-muted-foreground">Ora</th>
                    {data.days.map((d) => <th key={d} className="p-2 text-xs text-muted-foreground">{d}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {data.hours.map((h) => (
                    <tr key={h}>
                      <td className="p-1 text-xs font-semibold text-muted-foreground">{h}ª</td>
                      {data.days.map((d) => (
                        <td key={d} className="p-1">
                          <Input value={grids[t]?.[`${d}-${h}`] || ""} onChange={(e) => setCell(t, d, h, e.target.value)}
                            data-testid={`orario-cell-${t}-${d}-${h}`} className="h-9 text-xs text-center" placeholder="—" />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </TabsContent>
        ))}
      </Tabs>
    </Card>
  );
}
