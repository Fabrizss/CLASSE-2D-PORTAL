import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";

const FOOTBALL_SLOTS = {
  calcio7: [
    { id: "P", label: "P", x: 50, y: 91 },
    { id: "D1", label: "D", x: 25, y: 71 }, { id: "D2", label: "D", x: 75, y: 71 },
    { id: "C1", label: "C", x: 18, y: 46 }, { id: "C2", label: "C", x: 50, y: 42 }, { id: "C3", label: "C", x: 82, y: 46 },
    { id: "A1", label: "A", x: 50, y: 16 },
  ],
  calcio11: [
    { id: "P", label: "P", x: 50, y: 93 },
    { id: "D1", label: "D", x: 14, y: 76 }, { id: "D2", label: "D", x: 38, y: 80 }, { id: "D3", label: "D", x: 62, y: 80 }, { id: "D4", label: "D", x: 86, y: 76 },
    { id: "C1", label: "C", x: 20, y: 52 }, { id: "C2", label: "C", x: 40, y: 56 }, { id: "C3", label: "C", x: 60, y: 56 }, { id: "C4", label: "C", x: 80, y: 52 },
    { id: "A1", label: "A", x: 37, y: 20 }, { id: "A2", label: "A", x: 63, y: 20 },
  ],
};

const VOLLEY_SLOTS = {
  pallavolo: [
    { id: "Z4", label: "4", x: 18, y: 24 }, { id: "Z3", label: "3", x: 50, y: 24 }, { id: "Z2", label: "2", x: 82, y: 24 },
    { id: "Z5", label: "5", x: 18, y: 76 }, { id: "Z6", label: "6", x: 50, y: 76 }, { id: "Z1", label: "1", x: 82, y: 76 },
  ],
  volley3: [
    { id: "Z1", label: "1", x: 25, y: 74 }, { id: "Z2", label: "2", x: 75, y: 74 }, { id: "Z3", label: "3", x: 50, y: 26 },
  ],
};

export function FormationField({ sportType, team, canManage, onAssign }) {
  const [openSlot, setOpenSlot] = useState(null);
  const isFootball = sportType === "calcio7" || sportType === "calcio11";
  const slots = isFootball ? FOOTBALL_SLOTS[sportType] : VOLLEY_SLOTS[sportType];
  const members = team.members || [];
  const bench = members.filter((m) => !m.position);
  const occupant = (slotId) => members.find((m) => m.position === slotId);
  const current = openSlot ? occupant(openSlot) : null;

  return (
    <div data-testid={`formation-field-${team.id}`}>
      <div
        className={`relative w-full rounded-2xl overflow-hidden border-2 ${isFootball ? "bg-gradient-to-b from-emerald-600 to-emerald-700 border-emerald-400/40" : "bg-gradient-to-b from-amber-100 to-amber-200 border-amber-400/50"}`}
        style={{ aspectRatio: isFootball ? "2/3" : "3/2" }}
      >
        {isFootball ? (
          <>
            <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-16 h-16 rounded-full border-2 border-white/40" />
            <div className="absolute left-0 right-0 top-1/2 border-t-2 border-white/40" />
            <div className="absolute left-1/2 -translate-x-1/2 bottom-0 w-2/5 h-[12%] border-2 border-b-0 border-white/40 rounded-t-sm" />
          </>
        ) : (
          <>
            <div className="absolute left-0 right-0 top-0 border-t-4 border-white/70" />
            <div className="absolute left-0 right-0 top-1/2 border-t-2 border-dashed border-white/50" />
          </>
        )}
        {slots.map((s) => {
          const occ = occupant(s.id);
          return (
            <button key={s.id} type="button" onClick={() => canManage && setOpenSlot(s.id)} disabled={!canManage}
              data-testid={`formation-slot-${team.id}-${s.id}`}
              style={{ left: `${s.x}%`, top: `${s.y}%` }}
              className="absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center gap-1 group">
              <span className={`w-9 h-9 rounded-full grid place-items-center text-xs font-bold border-2 transition-transform group-hover:scale-110 ${
                occ ? "bg-white text-primary border-white shadow-md" : "bg-white/15 border-white/60 text-white"}`}>
                {occ ? occ.name?.[0]?.toUpperCase() : s.label}
              </span>
              {occ && <span className="text-[10px] font-semibold bg-black/40 text-white rounded-full px-1.5 py-0.5 max-w-[72px] truncate">{occ.name}</span>}
            </button>
          );
        })}
      </div>

      {bench.length > 0 && (
        <div className="mt-3">
          <p className="text-xs text-muted-foreground mb-1.5">Panchina (senza posizione)</p>
          <div className="flex flex-wrap gap-1.5" data-testid={`formation-bench-${team.id}`}>
            {bench.map((m) => <Badge key={m.user_id} variant="outline" className="rounded-full">{m.name}</Badge>)}
          </div>
        </div>
      )}

      <Dialog open={!!openSlot} onOpenChange={(o) => !o && setOpenSlot(null)}>
        <DialogContent className="max-w-xs">
          <DialogHeader>
            <DialogTitle className="font-head">Posizione {openSlot}</DialogTitle>
            <DialogDescription>Scegli chi gioca in questa posizione.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            {current && (
              <Button variant="outline" className="w-full rounded-full" data-testid="formation-remove-btn"
                onClick={() => { onAssign(current.user_id, null); setOpenSlot(null); }}>
                Rimuovi {current.name}
              </Button>
            )}
            <Select onValueChange={(uid) => { onAssign(uid, openSlot); setOpenSlot(null); }}>
              <SelectTrigger data-testid="formation-assign-select"><SelectValue placeholder="Assegna giocatore…" /></SelectTrigger>
              <SelectContent>
                {members.filter((m) => m.user_id !== current?.user_id).map((m) => (
                  <SelectItem key={m.user_id} value={m.user_id}>{m.name}{m.position ? ` (era ${m.position})` : ""}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
