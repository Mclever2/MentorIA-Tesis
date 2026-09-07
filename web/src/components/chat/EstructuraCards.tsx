import { motion } from "framer-motion";
import { AlertTriangle, FileText, Layers, Sparkles } from "lucide-react";

import type { Mensaje } from "@/types";

export default function EstructuraCards({
  estructura,
}: {
  estructura: NonNullable<Mensaje["estructura"]>;
}) {
  const { nombre, stats } = estructura;

  // Las secciones llegan en orden del documento, así que el capítulo de cada una
  // es el último encabezado de primer nivel visto ("2 MARCO TEÓRICO", "I
  // GENERALIDADES"). Agrupar por el primer dígito juntaba el «1 Título» de las
  // generalidades con el «1 Planteamiento» del plan, que son capítulos distintos.
  const ETIQUETA = /^((?:\d+|[IVXLC]+)(?:\.\d+)*)[.)]?\s+/;
  const capitulos = new Map<string, typeof stats>();
  let actual = "";
  for (const s of stats) {
    const m = s.seccion.trim().match(ETIQUETA);
    if (m && !m[1].includes(".")) actual = s.seccion.trim();
    const cap = m
      ? actual || `Capítulo ${m[1].split(".")[0]}`
      : actual || "Otras secciones";
    if (!capitulos.has(cap)) capitulos.set(cap, []);
    capitulos.get(cap)!.push(s);
  }

  const totalChars = stats.reduce((a, s) => a + s.chars, 0);
  const totalFrags = stats.reduce((a, s) => a + s.n_fragmentos, 0);
  const maxChars = Math.max(...stats.map((s) => s.chars), 1);

  return (
    <div className="w-full min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 text-sm text-muted-foreground mb-3 min-w-0">
        <div className="flex items-center gap-2 min-w-0 flex-1 max-w-full">
          <FileText className="w-4 h-4 text-primary shrink-0" />
          <span
            className="font-medium text-foreground truncate min-w-0"
            title={nombre}
          >
            {nombre}
          </span>
        </div>
        <span className="shrink-0 text-xs sm:text-sm text-muted-foreground/80">
          · {stats.length} secciones · {totalFrags} fragmentos ·{" "}
          {totalChars.toLocaleString("es")} caracteres indexados
        </span>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        {[...capitulos.entries()].map(([cap, secciones], i) => (
          <motion.div
            key={cap}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.07, duration: 0.4, ease: "easeOut" }}
            className="glass-scroll rounded-2xl p-4 min-w-0"
          >
            <div className="flex items-center gap-2 mb-2.5 min-w-0">
              <Layers className="w-4 h-4 text-primary shrink-0" />
              <span className="text-sm font-semibold truncate min-w-0">{cap}</span>
            </div>
            <ul className="space-y-2">
              {secciones.map((s) => {
                const debil = s.chars < 200;
                return (
                  <li key={s.seccion} className="text-[13px]">
                    <div className="flex items-center justify-between gap-2 min-w-0">
                      <div className="flex items-center gap-1.5 min-w-0 flex-1" title={s.seccion}>
                        {debil && (
                          <AlertTriangle className="w-3.5 h-3.5 text-[#FF9500] shrink-0" />
                        )}
                        {s.mejorado && (
                          <Sparkles className="w-3.5 h-3.5 text-[#34C759] shrink-0" />
                        )}
                        <span className="truncate min-w-0">{s.seccion}</span>
                      </div>
                      <span className="text-muted-foreground shrink-0 tabular-nums text-xs">
                        pág. {s.pagina_inicio}
                      </span>
                    </div>
                    <div className="mt-1 h-1 rounded-full bg-muted overflow-hidden">
                      <div
                        className={`h-full rounded-full ${debil ? "bg-[#FF9500]" : "bg-primary/70"}`}
                        style={{ width: `${Math.max(4, (s.chars / maxChars) * 100)}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          </motion.div>
        ))}
      </div>

      <p className="mt-3 text-xs text-muted-foreground">
        Las secciones con <AlertTriangle className="w-3 h-3 inline text-[#FF9500]" /> tienen poco
        contenido — probablemente aún no las has redactado. Ya puedes pedir la revisión en el chat.
      </p>
    </div>
  );
}
