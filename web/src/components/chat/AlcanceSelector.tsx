import { useEffect, useState } from "react";
import { Check, Loader2, Target } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { fijarAlcance, obtenerAlcance, type AlcanceInfo, type GrupoAlcance } from "@/lib/api";

interface AlcanceSelectorProps {
  docId: string;
  /** `alcance` viene del backend (con los ítems ya resueltos) para poder persistirlo. */
  onListo: (alcance: AlcanceInfo, total: boolean) => void;
  onCerrar?: () => void;
}

/**
 * "¿Qué partes ya están redactadas?"
 *
 * Un proyecto de tesis se escribe por partes durante meses. Sin declarar el
 * alcance, la red calificaba los 33 ítems y ponía 0 en todo lo que el estudiante
 * aún no había escrito, hundiendo una nota que no reflejaba su avance real.
 *
 * OJO: esto NO lanza la revisión. Solo deja registrado qué se toma en cuenta
 * cuando el estudiante la pida; por eso los botones dicen "guardar" y no
 * "evaluar" (decían "evaluar" y la gente esperaba que arrancara sola).
 */
export default function AlcanceSelector({ docId, onListo, onCerrar }: AlcanceSelectorProps) {
  const [grupos, setGrupos] = useState<GrupoAlcance[]>([]);
  const [conAvance, setConAvance] = useState<Set<string>>(new Set());
  const [elegidos, setElegidos] = useState<Set<string>>(new Set());
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const info = await obtenerAlcance(docId);
        if (!vivo) return;
        setGrupos(info.grupos);

        // Un grupo "tiene avance" si algún ítem suyo ya cuenta con texto escrito.
        const avance = new Set<string>();
        for (const g of info.grupos) {
          if (g.items.some((n) => (info.chars_por_item[String(n)] ?? 0) > 0)) avance.add(g.grupo);
        }
        setConAvance(avance);

        const sugeridos = (info.alcance as { grupos?: string[] })?.grupos ?? [];
        setElegidos(new Set(sugeridos.length ? sugeridos : [...avance]));
      } catch {
        /* sin catálogo: el chat sigue funcionando y evalúa todo */
      } finally {
        if (vivo) setCargando(false);
      }
    })();
    return () => {
      vivo = false;
    };
  }, [docId]);

  function alternar(grupo: string) {
    setElegidos((prev) => {
      const siguiente = new Set(prev);
      if (siguiente.has(grupo)) siguiente.delete(grupo);
      else siguiente.add(grupo);
      return siguiente;
    });
  }

  async function confirmar(todo: boolean) {
    setGuardando(true);
    try {
      const seleccion = todo ? grupos.map((g) => g.grupo) : [...elegidos];
      const res = await fijarAlcance(docId, todo ? { todo: true } : { grupos: seleccion });
      onListo(res.alcance, todo);
    } catch {
      onListo({ modo: "declarado", grupos: [...elegidos], items: [] }, todo);
    } finally {
      setGuardando(false);
    }
  }

  const nItems = grupos
    .filter((g) => elegidos.has(g.grupo))
    .reduce((acc, g) => acc + g.items.length, 0);

  if (cargando) {
    return (
      <div className="glass rounded-2xl p-5 flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" />
        Preparando las partes de tu proyecto…
      </div>
    );
  }

  return (
    <div className="glass rounded-2xl p-5">
      <div className="flex items-start gap-2.5">
        <span className="grid place-items-center w-8 h-8 rounded-xl bg-primary/10 text-primary shrink-0">
          <Target className="w-4 h-4" />
        </span>
        <div className="min-w-0">
          <p className="font-medium">¿Qué partes de tu proyecto ya están redactadas?</p>
          <p className="text-sm text-muted-foreground mt-0.5">
            Marqué lo que detecté con contenido. Lo que dejes sin marcar{" "}
            <strong className="text-foreground">no se califica y no te resta</strong>: queda
            pendiente para cuando lo escribas.
          </p>
          <p className="text-[12px] text-muted-foreground mt-1.5">
            Esto no inicia la revisión: solo define qué se toma en cuenta cuando la pidas.
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-1.5 sm:grid-cols-2">
        {grupos.map((g) => {
          const activo = elegidos.has(g.grupo);
          const avance = conAvance.has(g.grupo);
          return (
            <button
              key={g.grupo}
              onClick={() => alternar(g.grupo)}
              className={cn(
                "flex items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left transition-colors",
                activo
                  ? "border-primary/40 bg-primary/5"
                  : "border-border hover:bg-muted/60",
              )}
            >
              <span
                className={cn(
                  "grid place-items-center w-4 h-4 rounded-[5px] border shrink-0",
                  activo ? "bg-primary border-primary text-primary-foreground" : "border-muted-foreground/40",
                )}
              >
                {activo && <Check className="w-3 h-3" />}
              </span>
              <span className="min-w-0">
                <span className="block text-[13px] font-medium truncate">{g.grupo}</span>
                <span className="block text-[11px] text-muted-foreground">
                  {g.items.length} ítems{avance ? " · ya tienes avance" : " · sin redactar aún"}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={!elegidos.size || guardando} onClick={() => confirmar(false)}>
          {guardando ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
          Guardar lo marcado ({nItems} ítems)
        </Button>
        <Button size="sm" variant="ghost" disabled={guardando} onClick={() => confirmar(true)}>
          Ya está todo redactado (33 ítems)
        </Button>
        {onCerrar && (
          <Button size="sm" variant="ghost" className="ml-auto text-muted-foreground" onClick={onCerrar}>
            Ahora no
          </Button>
        )}
      </div>
    </div>
  );
}
