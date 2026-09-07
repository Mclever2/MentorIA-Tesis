import type { DocumentoInfo, EventoRun } from "@/lib/api";

export interface ItemRubrica {
  item_numero: number | string;
  criterio?: string;
  puntaje?: number;
  puntaje_actual?: number;
  maximo?: number;                 // máximo del ítem (juez por tipo, escala ponderada)
  observacion?: string;
  descripcion?: string;
}

export interface SesionDebate {
  veredicto: {
    veredicto_general?: string;
    justificacion?: string;
    items_confirmados?: number[];
    items_descartados?: number[];
    items_matizados?: number[];
  };
  panel: { subagente: string; contenido: string }[];
}

export interface AnalisisDetalle {
  run_id?: string;
  seccion: string;
  puntaje?: number | null;
  puntaje_max?: number | null;
  puntaje_inicial?: number | null;
  escala_max?: number;
  iteraciones?: number;
  max_iteraciones?: number;
  texto_mejorado?: string;
  feedback_auditor?: string;
  observaciones_metodologicas?: string;
  sugerencias_redactor?: string;
  errores_rubrica?: ItemRubrica[];
  evaluacion_inicial?: ItemRubrica[];
  evaluacion_final?: ItemRubrica[];
  consenso?: string;
  disenso?: string;
  debate?: { sesiones: SesionDebate[] };
  contexto_pdf?: string;
  contexto_cruzado?: string;
  contexto_teorico?: string;
  // Métrica complementaria (rúbrica del tipo, LLM-as-judge, /100). SOLO llega en la
  // revisión COMPLETA; la evaluación por secciones no corre el juez.
  metricas_juez?: MetricaJuez | null;
}

export interface AccionMensaje {
  label: string;
  variante?: "primaria" | "secundaria";
  flags: { confirmar_reevaluacion?: boolean; decision_mejoras?: "aplicar" | "mantener" } | null;
}

// Calificación por ítem de la revisión completa.
export interface RubricaItemEval {
  numero: number | string;
  descripcion: string;
  secciones?: string[];
  puntaje: number | null;          // null = no aplica por tipo
  maximo: number;
  // "fuera_alcance" = el estudiante no pidió evaluar esta parte: ni suma ni resta.
  estado: "ok" | "bajo" | "na" | "ausente" | "fuera_alcance";
  razon?: string;
}

export interface RevisionCompleta {
  calificacion: {
    puntaje: number;
    maximo: number;
    items: RubricaItemEval[];
    items_evaluados?: number;
    items_rubrica?: number;
    items_fuera?: number;
  };
  nota_vigesimal?: number | null;   // tabla oficial UPAO (0-99 → 0-20)
  fortalezas?: string[];
  debilidades?: string[];
  trazabilidad?: { coherente: boolean; observaciones: string };
  // Alcance con el que se calificó: si `total` es false la nota es PARCIAL y se
  // debe mostrar junto al avance sobre los 33 ítems de la rúbrica.
  alcance?: {
    total: boolean;
    grupos: string[];
    items_evaluados: number;
    items_rubrica: number;
  };
}

// Métrica complementaria: rúbrica del tipo evaluada por LLM-as-judge (escala /100).
export interface MetricaJuez {
  tipo: string;
  fuente?: string;
  calificacion: { puntaje: number; maximo: number; items: RubricaItemEval[] };
}

/** Texto largo pegado por el estudiante: viaja como adjunto, no como muro de texto. */
export interface AdjuntoTexto {
  id: string;
  nombre: string;
  texto: string;
  lineas: number;
  chars: number;
}

export interface Mensaje {
  id: string;
  rol: "user" | "assistant";
  contenido: string;
  tipo?: "texto" | "estructura";
  estructura?: Pick<DocumentoInfo, "nombre" | "stats" | "estructura_toc">;
  detalles?: AnalisisDetalle[];
  revision?: RevisionCompleta;
  acciones?: AccionMensaje[];
  // Adjuntos mostrados como chip (el contenido no se vuelca en la burbuja).
  adjuntos?: AdjuntoTexto[];
}

export interface Conversacion {
  id: string;
  titulo: string;
  creada_en: string;
}

// Rúbrica OFICIAL UPAO (fija — el estudiante ya no puede subir la suya).
export interface RubricaItemDef {
  numero: number;
  descripcion: string;
}

export interface RubricaUpaoInfo {
  nombre: string;
  total_items: number;
  escala_max: number;
  escala: Record<string, string>;            // "3" → "Excelente", …
  puntaje_maximo: number;
  grupos: { titulo: string; items: RubricaItemDef[] }[];
  // Ítems mapeados a las secciones REALES del proyecto activo (null si aún no
  // hay proyecto: el mapeo se calcula automáticamente al subirlo).
  mapa_secciones?: Record<string, number[]> | null;
}

// Reglamento UPAO fijo: identificación, vigencia y puntos que afectan la tesis.
export interface ReglamentoInfo {
  titulo: string;
  universidad: string;
  codigo: string;
  version: string;
  vigencia: string;
  resolucion: string;
  deroga: string;
  nota_vigencia: string;
  puntos: { ref: string; texto: string }[];
  perfil_agentes: string;
}

export interface PasoProgreso {
  id: number;
  texto: string;
  estado: "activo" | "completado";
}

export type { DocumentoInfo, EventoRun };
