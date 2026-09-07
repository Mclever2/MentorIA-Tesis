import { supabase } from "./supabase";
import type { ReglamentoInfo, RubricaUpaoInfo } from "@/types";

const API_URL = (import.meta.env.VITE_API_URL as string | undefined) || "";

export interface SeccionStat {
  seccion: string;
  pagina_inicio: number;
  chars: number;
  n_fragmentos: number;
  mejorado?: boolean;
}

export interface DocumentoInfo {
  doc_id: string;
  nombre: string;
  hash: string;
  ya_indexado: boolean;
  estructura_toc: Record<string, number>;
  stats: SeccionStat[];
  /** De dónde vino el proyecto: "pdf" | "docx" | "texto". */
  formato?: string;
  /** Con qué señal se resolvió la estructura (estilos de Word, marcadores, índice…). */
  origen_estructura?: string;
  /** Avisos de la indexación (páginas sin texto, índice desfasado, sin encabezados…). */
  avisos?: string[];
  alcance?: AlcanceInfo;
}

/** Qué partes del proyecto se someten a evaluación. */
export interface AlcanceInfo {
  modo: "auto" | "declarado";
  grupos: string[];
  items: number[];
}

export interface GrupoAlcance {
  grupo: string;
  items: number[];
  descripcion: string;
}

export interface CatalogoAlcance {
  grupos: GrupoAlcance[];
  alcance: AlcanceInfo | Record<string, never>;
  /** Ítem → caracteres escritos en el proyecto: permite marcar qué ya tiene avance. */
  chars_por_item: Record<string, number>;
}

export interface ChatRespuesta {
  tipo: "conversacion" | "run" | "confirmacion";
  respuesta?: string;
  run_id?: string;
  modo?: "completo" | "secciones";
  secciones?: string[];
  subtipo?: "reevaluar" | "aplicar_mejoras";
  mensaje?: string;
  mejoras_aplicadas?: string[];
}

export interface ChatFlags {
  confirmar_reevaluacion?: boolean;
  decision_mejoras?: "aplicar" | "mantener";
}

export interface EventoRun {
  tipo: string;
  [key: string]: unknown;
}

async function authHeaders(): Promise<Record<string, string>> {
  if (!supabase) return {};
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function manejarError(res: Response): Promise<never> {
  let detalle = `Error ${res.status}`;
  try {
    const body = await res.json();
    detalle = body.detail || detalle;
  } catch {
    /* respuesta sin JSON */
  }
  throw new Error(detalle);
}

export interface DocMemoria {
  evaluadas: string[];
  aplicadas: Record<string, string>;
  pendientes: Record<string, string>;
  // Resumen de la última evaluación, para que el chat rápido no pierda el hilo.
  ultima_revision?: { tipo?: string; texto?: string };
}

/** Origen del proyecto: un archivo, texto pegado o un enlace de Google Docs. */
export type FuenteDocumento =
  | { tipo: "archivo"; archivo: File }
  | { tipo: "texto"; texto: string; nombre?: string }
  | { tipo: "enlace"; enlace: string };

export async function subirDocumento(
  fuente: File | FuenteDocumento,
  memoria?: DocMemoria | null,
): Promise<DocumentoInfo> {
  const form = new FormData();
  const origen: FuenteDocumento =
    fuente instanceof File ? { tipo: "archivo", archivo: fuente } : fuente;

  if (origen.tipo === "archivo") {
    form.append("archivo", origen.archivo);
  } else if (origen.tipo === "texto") {
    form.append("texto", origen.texto);
    form.append("nombre", origen.nombre ?? "Texto pegado");
  } else {
    form.append("enlace", origen.enlace);
  }
  if (memoria) form.append("memoria", JSON.stringify(memoria));
  const res = await fetch(`${API_URL}/api/documentos`, {
    method: "POST",
    headers: await authHeaders(),
    body: form,
  });
  if (!res.ok) await manejarError(res);
  return res.json();
}

/** Texto pegado cuando YA hay proyecto: se ubica en una sección y se guarda como
 *  versión de trabajo, sin pisar el documento original. */
export async function agregarFragmento(
  docId: string,
  texto: string,
  nombre = "Texto pegado",
): Promise<{ seccion: string | null; mensaje: string }> {
  const res = await fetch(`${API_URL}/api/fragmento`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ doc_id: docId, texto, nombre }),
  });
  if (!res.ok) await manejarError(res);
  return res.json();
}

/** Grupos evaluables + alcance actual del proyecto. */
export async function obtenerAlcance(docId: string): Promise<CatalogoAlcance> {
  const res = await fetch(`${API_URL}/api/alcance?doc_id=${encodeURIComponent(docId)}`, {
    headers: await authHeaders(),
  });
  if (!res.ok) await manejarError(res);
  return res.json();
}

/** Declara qué partes del proyecto quiere el estudiante que se evalúen. */
export async function fijarAlcance(
  docId: string,
  opciones: { grupos?: string[]; todo?: boolean },
): Promise<{ alcance: AlcanceInfo }> {
  const res = await fetch(`${API_URL}/api/alcance`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ doc_id: docId, grupos: opciones.grupos ?? null, todo: !!opciones.todo }),
  });
  if (!res.ok) await manejarError(res);
  return res.json();
}

/** Rúbrica oficial UPAO (fija). Con `docId` incluye el mapeo ítem→secciones del proyecto. */
export async function obtenerRubricaUpao(docId?: string | null): Promise<RubricaUpaoInfo> {
  const qs = docId ? `?doc_id=${encodeURIComponent(docId)}` : "";
  const res = await fetch(`${API_URL}/api/rubrica${qs}`, {
    headers: await authHeaders(),
  });
  if (!res.ok) await manejarError(res);
  return res.json();
}

/** Reglamento UPAO fijo: vigencia, resolución y puntos que afectan la tesis. */
export async function obtenerReglamentoUpao(): Promise<ReglamentoInfo> {
  const res = await fetch(`${API_URL}/api/reglamento`, {
    headers: await authHeaders(),
  });
  if (!res.ok) await manejarError(res);
  return res.json();
}

export async function obtenerBiblioteca(): Promise<{
  libros: { nombre: string; fragmentos: number }[];
  total_fragmentos: number;
}> {
  const res = await fetch(`${API_URL}/api/biblioteca`, {
    headers: await authHeaders(),
  });
  if (!res.ok) await manejarError(res);
  return res.json();
}

export async function enviarChat(body: {
  mensaje: string;
  doc_id: string | null;
  conversacion_id?: string | null;
  max_iteraciones: number;
  contexto_previo: string;
  historial?: { rol: string; contenido: string }[];
} & ChatFlags): Promise<ChatRespuesta> {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify(body),
  });
  if (!res.ok) await manejarError(res);
  return res.json();
}

/** Ping de presencia para medir el tiempo de uso. No bloquea ni lanza error. */
export async function enviarHeartbeat(conversacionId: string | null): Promise<void> {
  try {
    await fetch(`${API_URL}/api/heartbeat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(await authHeaders()) },
      body: JSON.stringify({ conversacion_id: conversacionId }),
      keepalive: true,
    });
  } catch {
    /* silencioso: la analítica nunca debe romper la app */
  }
}

export async function cancelarRun(runId: string) {
  const res = await fetch(`${API_URL}/api/runs/${runId}/cancelar`, {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!res.ok) await manejarError(res);
  return res.json();
}

export async function streamRun(
  runId: string,
  onEvento: (e: EventoRun) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/api/runs/${runId}/stream`, {
    headers: await authHeaders(),
    signal,
  });
  if (!res.ok || !res.body) await manejarError(res);

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const bloques = buffer.split("\n\n");
    buffer = bloques.pop() ?? "";
    for (const bloque of bloques) {
      const linea = bloque.split("\n").find((l) => l.startsWith("data: "));
      if (!linea) continue;
      try {
        onEvento(JSON.parse(linea.slice(6)) as EventoRun);
      } catch {
        /* evento malformado: ignorar */
      }
    }
  }
}
