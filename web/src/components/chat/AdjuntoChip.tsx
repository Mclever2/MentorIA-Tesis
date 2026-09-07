import { useState } from "react";
import { FileText, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { AdjuntoTexto } from "@/types";

interface AdjuntoChipProps {
  adjunto: AdjuntoTexto;
  onQuitar?: () => void;
  compacto?: boolean;
}

/**
 * Píldora para el texto largo que el estudiante pega en el chat.
 *
 * Pegar media sección dentro de la burbuja hacía ilegible la conversación: el
 * mensaje real quedaba enterrado bajo miles de caracteres. Aquí el contenido se
 * resume en un chip —igual que un archivo adjunto— y se consulta al abrirlo.
 */
export default function AdjuntoChip({ adjunto, onQuitar, compacto }: AdjuntoChipProps) {
  const [abierto, setAbierto] = useState(false);

  return (
    <>
      <div
        className={cn(
          "inline-flex items-center gap-2 rounded-xl border border-border bg-card/70",
          "px-2.5 py-1.5 max-w-[260px] transition-colors hover:bg-card",
          compacto && "py-1",
        )}
      >
        <button
          type="button"
          onClick={() => setAbierto(true)}
          className="flex items-center gap-2 min-w-0 text-left"
          title="Ver el texto pegado"
        >
          <span className="grid place-items-center w-7 h-7 rounded-lg bg-primary/10 text-primary shrink-0">
            <FileText className="w-3.5 h-3.5" />
          </span>
          <span className="min-w-0">
            <span className="block text-[13px] font-medium truncate">{adjunto.nombre}</span>
            <span className="block text-[11px] text-muted-foreground">
              TXT · {adjunto.lineas.toLocaleString("es")} líneas ·{" "}
              {adjunto.chars.toLocaleString("es")} caracteres
            </span>
          </span>
        </button>

        {onQuitar && (
          <button
            type="button"
            onClick={onQuitar}
            title="Quitar"
            className="shrink-0 rounded-full p-1 text-muted-foreground hover:text-foreground hover:bg-muted"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {abierto && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"
          onClick={() => setAbierto(false)}
        >
          <div
            className="w-full max-w-2xl max-h-[80vh] flex flex-col rounded-2xl bg-card border border-border shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-3 border-b border-border">
              <div className="min-w-0">
                <p className="font-medium truncate">{adjunto.nombre}</p>
                <p className="text-xs text-muted-foreground">
                  {adjunto.lineas.toLocaleString("es")} líneas ·{" "}
                  {adjunto.chars.toLocaleString("es")} caracteres
                </p>
              </div>
              <button
                onClick={() => setAbierto(false)}
                className="rounded-full p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <pre className="flex-1 overflow-auto px-5 py-4 text-[13px] whitespace-pre-wrap font-sans">
              {adjunto.texto}
            </pre>
          </div>
        </div>
      )}
    </>
  );
}
