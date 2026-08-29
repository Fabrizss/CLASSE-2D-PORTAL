import { useEffect, useState, useRef, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FileText, Droplets, Pizza, Heart, Hand } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const CONFIG = {
  foglietto: { icon: FileText, color: "#FBBF24", label: "ti ha lanciato un foglietto" },
  secchio: { icon: Droplets, color: "#38BDF8", label: "ti ha rovesciato un secchio d'acqua" },
  pizza: { icon: Pizza, color: "#F97316", label: "ti ha lanciato una pizza" },
  cuore: { icon: Heart, color: "#F472B6", label: "ti ha mandato un cuore" },
  high_five: { icon: Hand, color: "#7C3AED", label: "ti ha dato il cinque" },
};

export function playP2P(type, from) {
  window.dispatchEvent(new CustomEvent("p2p-play", { detail: { type, from } }));
}

function Anim({ item, onDone }) {
  const cfg = CONFIG[item.type] || CONFIG.foglietto;
  const Icon = cfg.icon;
  useEffect(() => {
    const t = setTimeout(onDone, 2200);
    return () => clearTimeout(t);
  }, [onDone]);

  if (item.type === "secchio") {
    return (
      <motion.div className="fixed inset-0 z-[200] pointer-events-none overflow-hidden"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
        <motion.div className="absolute inset-0 bg-sky-400/25"
          initial={{ y: "-100%" }} animate={{ y: 0 }} transition={{ duration: 0.5 }} />
        {[...Array(14)].map((_, i) => (
          <motion.div key={i} className="absolute" style={{ left: `${(i * 7) % 100}%`, color: cfg.color }}
            initial={{ y: -80, opacity: 0 }} animate={{ y: "110vh", opacity: 1 }}
            transition={{ duration: 1.4, delay: (i % 5) * 0.08 }}>
            <Droplets size={26 + (i % 3) * 8} />
          </motion.div>
        ))}
      </motion.div>
    );
  }
  if (item.type === "cuore") {
    return (
      <div className="fixed inset-0 z-[200] pointer-events-none overflow-hidden">
        {[...Array(12)].map((_, i) => (
          <motion.div key={i} className="absolute bottom-0" style={{ left: `${10 + i * 7}%`, color: cfg.color }}
            initial={{ y: 0, opacity: 0, scale: 0.5 }} animate={{ y: "-90vh", opacity: [0, 1, 0], scale: 1 }}
            transition={{ duration: 2, delay: (i % 6) * 0.1 }}>
            <Heart fill={cfg.color} size={22 + (i % 3) * 10} />
          </motion.div>
        ))}
      </div>
    );
  }
  const spin = item.type === "pizza";
  return (
    <div className="fixed inset-0 z-[200] pointer-events-none">
      <motion.div className="absolute" style={{ color: cfg.color, top: "40%" }}
        initial={{ x: "-15vw", y: 0, rotate: 0, scale: 0.6 }}
        animate={{ x: "110vw", y: [0, -120, 40, -60, 0], rotate: spin ? 720 : 360, scale: 1.2 }}
        transition={{ duration: 1.6, ease: "easeInOut" }}>
        <Icon size={72} strokeWidth={1.5} />
      </motion.div>
    </div>
  );
}

export default function P2PLayer() {
  const [queue, setQueue] = useState([]);
  const seen = useRef(new Set());

  const push = useCallback((item) => setQueue((q) => [...q, { ...item, key: Math.random() }]), []);

  useEffect(() => {
    const onPlay = (e) => push({ type: e.detail.type });
    window.addEventListener("p2p-play", onPlay);
    return () => window.removeEventListener("p2p-play", onPlay);
  }, [push]);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const { data } = await api.get("/actions/inbox");
        if (!alive) return;
        data.forEach((a) => {
          if (seen.current.has(a.id)) return;
          seen.current.add(a.id);
          const cfg = CONFIG[a.type] || CONFIG.foglietto;
          toast(`${a.from_user_name} ${cfg.label}!`);
          push({ type: a.type });
        });
      } catch {}
    };
    poll();
    const iv = setInterval(poll, 2000);
    return () => { alive = false; clearInterval(iv); };
  }, [push]);

  return (
    <AnimatePresence>
      {queue.map((item) => (
        <Anim key={item.key} item={item} onDone={() => setQueue((q) => q.filter((x) => x.key !== item.key))} />
      ))}
    </AnimatePresence>
  );
}
