import { Building2, ClipboardList, Eye } from "lucide-react";

import { Button } from "@/components/ui/button";

interface Props {
  hayProyecto: boolean;
  onVerRubrica: () => void;
  onVerReglamento: () => void;
}

/**
 * Panel de recursos FIJOS: la rúbrica y el reglamento oficiales UPAO.
 * El estudiante ya no puede subirlos ni reemplazarlos — solo consultarlos.
 */
export default function RecursosPanel(props: Props) {
  return (
    <div className="px-4 pb-3 space-y-3">
      {/* ── Rúbrica oficial UPAO ─────────────────────────────── */}
      <div className="glass rounded-2xl p-3.5">
        <div className="flex items-center gap-2 text-sm font-medium mb-2">
          <ClipboardList className="w-4 h-4 text-primary" />
          Rúbrica de evaluación
        </div>

        <p className="text-[11.5px] text-muted-foreground mb-2 leading-snug">
          Ficha oficial UPAO · 33 ítems · escala 0–3 (máx. 99 pts)
        </p>

        <Button
          size="sm"
          variant="outline"
          className="rounded-full h-7 text-[12px] gap-1"
          onClick={props.onVerRubrica}
        >
          <Eye className="w-3 h-3" /> Ver ítems
        </Button>
        {!props.hayProyecto && (
          <p className="mt-1.5 text-[10.5px] text-muted-foreground">
            Al subir tu proyecto, cada ítem se mapea automáticamente a sus secciones.
          </p>
        )}
      </div>

      {/* ── Reglamento UPAO ──────────────────────────────────── */}
      <div className="glass rounded-2xl p-3.5">
        <div className="flex items-center gap-2 text-sm font-medium mb-2">
          <Building2 className="w-4 h-4 text-primary" />
          Reglamento UPAO
        </div>

        <p className="text-[11.5px] text-muted-foreground mb-2 leading-snug">
          Reglamento de Investigación e Innovación
          <br />
          <span className="opacity-70">INS-VIN-RG-04 v01 · vigente desde 27/05/2026</span>
        </p>

        <Button
          size="sm"
          variant="outline"
          className="rounded-full h-7 text-[12px] gap-1"
          onClick={props.onVerReglamento}
        >
          <Eye className="w-3 h-3" /> Ver
        </Button>
        <p className="mt-1.5 text-[10.5px] text-muted-foreground">
          Los agentes adaptan su criterio a este reglamento en todas las revisiones.
        </p>
      </div>
    </div>
  );
}
