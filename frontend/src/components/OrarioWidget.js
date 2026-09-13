import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarClock, StickyNote } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

const TYPE_LABEL = { provvisorio: "Provvisorio", settimana: "Settimana specifica", definitivo: "Definitivo" };

export function OrarioWidget() {
  const [data, setData] = useState(null);
  const [cell, setCell] = useState(null);
  const [form, setForm] = useState({ subject: "", note: "" });

  const load = () => api.get("/orario").then((r) => setData(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const openCell = (day, hour) => {
    const key = `${day}-${hour}`;
    const ov = data.my_overrides[key] || {};
    setForm({ subject: ov.subject || "", note: ov.note || "" });
    setCell({ day, hour, key });
  };

  const saveCell = async () => {
    try {
      await api.post("/orario/personal", { cell: cell.key, subject: form.subject, note: form.note });
      toast.success("Salvato");
      setCell(null);
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!data) return null;

  return (
    <Card className="p-6 border-border" data-testid="orario-widget">
      <div className="flex items-center gap-2 mb-1 flex-wrap">
        <CalendarClock size={18} className="text-primary" />
        <h2 className="font-head text-xl font-bold tracking-tight">Orario</h2>
        <Badge variant="outline" className="rounded-full">{TYPE_LABEL[data.active_type]}</Badge>
        {data.week_label && <span className="text-xs text-muted-foreground">{data.week_label}</span>}
      </div>
      <p className="text-muted-foreground text-sm mb-4">Clicca una cella per aggiungere un tuo appunto personale, visibile solo a te.</p>
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
                <td className="p-1.5 text-xs font-semibold text-muted-foreground">{h}ª</td>
                {data.days.map((d) => {
                  const key = `${d}-${h}`;
                  const official = data.grid[key];
                  const ov = data.my_overrides[key];
                  const shown = ov?.subject || official;
                  return (
                    <td key={d} className="p-1">
                      <button onClick={() => openCell(d, h)} data-testid={`orario-widget-cell-${d}-${h}`}
                        className={`w-full h-12 rounded-lg text-xs px-1 flex flex-col items-center justify-center gap-0.5 border transition-colors ${
                          shown ? "bg-primary/10 border-primary/20 hover:bg-primary/20" : "border-border hover:bg-secondary/50"}`}>
                        <span className="truncate w-full text-center">{shown || "—"}</span>
                        {ov?.note && <StickyNote size={10} className="text-amber-500" />}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!cell} onOpenChange={(o) => !o && setCell(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="font-head">{cell?.day} · {cell?.hour}ª ora</DialogTitle>
            <DialogDescription>Modifiche visibili solo a te, non cambiano l'orario ufficiale.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-xs font-semibold text-muted-foreground">Materia personale (opzionale)</label>
              <Input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} data-testid="orario-personal-subject-input" className="mt-1" placeholder="Sostituisci la materia solo per te" />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted-foreground">Appunto</label>
              <Textarea value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} data-testid="orario-personal-note-input" className="mt-1" placeholder="Es. Portare il libro di lettura" />
            </div>
          </div>
          <DialogFooter>
            <Button onClick={saveCell} data-testid="orario-personal-save-btn" className="rounded-full w-full">Salva</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
