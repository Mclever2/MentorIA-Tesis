import { motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowLeft,
  Award,
  CheckCircle2,
  CircleDashed,
  Link2,
  MinusCircle,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { RevisionCompleta, RubricaItemEval } from "@/types";

const ESTADO = {
  ok:      { icon: CheckCircle2,  color: "text-[#34C759]",        label: "Cumple" },
  bajo:    { icon: AlertTriangle, color: "text-[#FF9500]",        label: "Mejorable" },
  na:      { icon: MinusCircle,   color: "text-muted-foreground", label: "No aplica (tipo)" },
  ausente: { icon: XCircle,       color: "text-destructive",      label: "Ausente" },
  // El estudiante no pidió evaluar esta parte: se muestra apagado y sin puntaje
  // para que quede claro que no entra en la nota ni en su contra.
  fuera_alcance: { icon: CircleDashed, color: "text-muted-foreground", label: "No evaluado" },
} as const;

function Fila({ it }: { it: RubricaItemEval }) {
  const meta = ESTADO[it.estado] ?? ESTADO.bajo;
  const Icon = meta.icon;
  const fuera = it.estado === "fuera_alcance";
  return (
    <li className={cn("py-2.5 border-b border-border/60 last:border-0", fuera && "opacity-55")}>
      <div className="flex items-start gap-3">
        <span className="shrink-0 w-8 h-8 rounded-xl bg-muted grid place-items-center text-xs font-semibold">
          {String(it.numero).padStart(2, "0")}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] leading-snug">{it.descripcion}</p>
          {it.razon && <p className="mt-1 text-xs text-muted-foreground leading-snug">{it.razon}</p>}
          {it.secciones && it.secciones.length > 0 && (
            <p className="mt-1 text-[11px] text-muted-foreground">{it.secciones.join(" · ")}</p>
          )}
        </div>
        <div className="shrink-0 text-right">
          <div className={cn("flex items-center gap-1 justify-end text-xs font-medium", meta.color)}>
            <Icon className="w-3.5 h-3.5" /> {meta.label}
          </div>
          <div className="mt-0.5 text-sm font-semibold tabular-nums">
            {it.puntaje == null ? "—" : `${it.puntaje}/${it.maximo}`}
          </div>
        </div>
      </div>
    </li>
  );
}

export default function RevisionCompletaPanel({
  revision,
  onCerrar,
}: {
  revision: RevisionCompleta;
  onCerrar: () => void;
}) {
  const { calificacion, nota_vigesimal, fortalezas, debilidades, trazabilidad, alcance } = revision;
  const items = calificacion?.items ?? [];
  // Con alcance parcial la nota es SOBRE LO DECLARADO: hay que decirlo, o el
  // estudiante creerá que ésa es su nota de sustentación (que va sobre 33 ítems).
  const parcial = alcance ? !alcance.total : false;
  const evaluados = alcance?.items_evaluados ?? calificacion?.items_evaluados ?? items.length;
  const totalRubrica = alcance?.items_rubrica ?? calificacion?.items_rubrica ?? items.length;
  const ratio = calificacion?.maximo ? calificacion.puntaje / calificacion.maximo : 0;
  const color =
    ratio >= 0.8 ? "text-[#34C759]" : ratio >= 0.5 ? "text-[#FF9500]" : "text-destructive";

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="absolute inset-0 z-30 bg-background flex flex-col"
    >
      <div className="border-b border-border bg-card/60 backdrop-blur-xl">
        <div className="mx-auto max-w-4xl px-5 py-4 flex items-center gap-3">
          <Button variant="ghost" size="icon" className="rounded-full" onClick={onCerrar}>
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <div className="min-w-0">
            <h1 className="font-semibold text-lg">
              {parcial ? "Calificación de lo que elegiste evaluar" : "Calificación con la rúbrica UPAO"}
            </h1>
            <p className="text-xs text-muted-foreground">
              {evaluados} de {totalRubrica} ítems de la rúbrica · escala 0–3 por ítem
              {parcial && alcance?.grupos?.length ? ` · ${alcance.grupos.join(", ").toLowerCase()}` : ""}
            </p>
          </div>
          <div className="ml-auto text-right">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              {parcial ? "Sobre lo entregado" : "Total"}
            </div>
            <div className={cn("text-xl font-bold tabular-nums", color)}>
              {calificacion?.puntaje ?? 0}/{calificacion?.maximo ?? 0} pts
            </div>
            {nota_vigesimal != null && (
              <div className="text-[11px] text-muted-foreground tabular-nums">
                {parcial ? "≈" : "nota vigesimal ≈"} {nota_vigesimal}/20
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-5 py-6 space-y-5">
          {parcial && (
            <section className="rounded-3xl border border-primary/25 bg-primary/5 p-4">
              <p className="text-sm">
                <strong>Esta nota mide solo lo que entregaste.</strong> Has cubierto{" "}
                <strong>{evaluados} de {totalRubrica}</strong> ítems de la rúbrica UPAO
                {totalRubrica ? ` (${Math.round((evaluados * 100) / totalRubrica)} %)` : ""}. Los
                ítems marcados «No evaluado» quedaron fuera del alcance que elegiste:{" "}
                <strong>no restan</strong>. La nota de la sustentación se calcula sobre los{" "}
                {totalRubrica} ítems, así que úsala como avance, no como nota final.
              </p>
            </section>
          )}
          {trazabilidad && (
            <section className="glass-scroll rounded-3xl p-5">
              <h2 className="font-semibold flex items-center gap-2 mb-2">
                <Link2 className="w-4 h-4 text-primary" /> Trazabilidad
                <span
                  className={cn(
                    "text-xs font-medium",
                    trazabilidad.coherente ? "text-[#34C759]" : "text-[#FF9500]",
                  )}
                >
                  {trazabilidad.coherente ? "coherente" : "con observaciones"}
                </span>
              </h2>
              <p className="text-[13px] text-muted-foreground leading-relaxed">
                {trazabilidad.observaciones || "Sin observaciones."}
              </p>
            </section>
          )}

          {(fortalezas?.length || debilidades?.length) ? (
            <div className="grid sm:grid-cols-2 gap-5">
              <section className="glass-scroll rounded-3xl p-5">
                <h2 className="font-semibold mb-2">Fortalezas</h2>
                {fortalezas?.length ? (
                  <ul className="list-disc pl-5 text-[13px] space-y-1">
                    {fortalezas.map((f, i) => <li key={i}>{f}</li>)}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">—</p>
                )}
              </section>
              <section className="glass-scroll rounded-3xl p-5">
                <h2 className="font-semibold mb-2">Debilidades</h2>
                {debilidades?.length ? (
                  <ul className="list-disc pl-5 text-[13px] space-y-1">
                    {debilidades.map((d, i) => <li key={i}>{d}</li>)}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">—</p>
                )}
              </section>
            </div>
          ) : null}

          <section className="glass-scroll rounded-3xl p-5">
            <h2 className="font-semibold flex items-center gap-2 mb-3">
              <Award className="w-4 h-4 text-primary" /> Calificación con la rúbrica UPAO · por ítem
            </h2>
            <ul>{items.map((it) => <Fila key={it.numero} it={it} />)}</ul>
          </section>
        </div>
      </div>
    </motion.div>
  );
}
