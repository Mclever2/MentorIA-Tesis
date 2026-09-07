import { motion } from "framer-motion";
import { ArrowLeft, BadgeCheck, Building2, ScrollText } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ReglamentoInfo } from "@/types";

export default function ReglamentoModal({
  reglamento,
  onCerrar,
}: {
  reglamento: ReglamentoInfo;
  onCerrar: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="absolute inset-0 z-30 bg-background flex flex-col"
    >
      <div className="border-b border-border bg-card/60 backdrop-blur-xl">
        <div className="mx-auto max-w-3xl px-5 py-4 flex items-center gap-3">
          <Button variant="ghost" size="icon" className="rounded-full" onClick={onCerrar}>
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <div className="min-w-0">
            <h1 className="font-semibold text-lg truncate flex items-center gap-2">
              <Building2 className="w-5 h-5 text-primary" />
              {reglamento.titulo}
            </h1>
            <p className="text-xs text-muted-foreground">
              {reglamento.universidad} · {reglamento.codigo} · versión {reglamento.version}
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-5 py-6 space-y-5">
          {/* ── Vigencia ─────────────────────────────────────── */}
          <section className="glass-scroll rounded-3xl p-5">
            <h2 className="font-semibold flex items-center gap-2 mb-2">
              <BadgeCheck className="w-4 h-4 text-[#34C759]" /> Vigencia
              <span className="text-xs font-medium text-[#34C759]">
                vigente desde {reglamento.vigencia}
              </span>
            </h2>
            <p className="text-[13px] leading-relaxed text-muted-foreground">
              {reglamento.nota_vigencia}
            </p>
            <p className="mt-2 text-[12px] text-muted-foreground">
              Aprobado por {reglamento.resolucion}. Deroga el {reglamento.deroga}.
            </p>
          </section>

          {/* ── Puntos que afectan tu proyecto ───────────────── */}
          <section className="glass-scroll rounded-3xl p-5">
            <h2 className="font-semibold flex items-center gap-2 mb-3">
              <ScrollText className="w-4 h-4 text-primary" /> Puntos que afectan tu proyecto
            </h2>
            <ul>
              {reglamento.puntos.map((p, i) => (
                <li key={i} className="py-2.5 border-b border-border/60 last:border-0">
                  <div className="flex items-start gap-3">
                    <span className="shrink-0 text-[11px] font-semibold bg-muted rounded-xl px-2 py-1 whitespace-nowrap">
                      {p.ref}
                    </span>
                    <p className="text-[13px] leading-snug">{p.texto}</p>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          {/* ── Cómo modula a los agentes ────────────────────── */}
          <section className="glass-scroll rounded-3xl p-5">
            <h2 className="font-semibold mb-2">Cómo adapta la conducta de los agentes</h2>
            <p className="text-[14px] leading-relaxed whitespace-pre-wrap text-muted-foreground">
              {reglamento.perfil_agentes}
            </p>
          </section>

          <p className="text-[11px] text-muted-foreground text-center">
            Este reglamento es fijo: los agentes lo aplican en todas las revisiones y no se
            puede reemplazar por otro.
          </p>
        </div>
      </div>
    </motion.div>
  );
}
