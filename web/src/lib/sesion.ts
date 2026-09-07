// Persistencia de la sesión por chat: el documento en Supabase Storage + su
// metadata en la fila de la conversación. Permite reabrir un chat del historial
// y re-indexar el proyecto para seguir el hilo exactamente donde quedó.
//
// El archivo ya no es necesariamente un PDF: puede ser Word, texto plano o el
// texto que el estudiante pegó en el chat, así que la ruta y el content-type se
// derivan del propio archivo en vez de asumir ".pdf".
import { subirDocumento, type AlcanceInfo, type DocMemoria, type DocumentoInfo } from "@/lib/api";
import { supabase } from "@/lib/supabase";

const BUCKET = "tesis";

export interface DocPersistido {
  nombre: string;
  hash: string;
  storagePath: string;
  toc: Record<string, number>;
  stats: DocumentoInfo["stats"];
  memoria: DocMemoria;
  /** Alcance declarado por el estudiante; se reaplica al reabrir el chat. */
  alcance: AlcanceInfo | null;
}

const TIPOS_POR_EXTENSION: Record<string, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  txt: "text/plain",
  md: "text/markdown",
  markdown: "text/markdown",
};

function extensionDe(nombre: string): string {
  const ext = nombre.toLowerCase().split(".").pop() ?? "";
  return ext in TIPOS_POR_EXTENSION ? ext : "txt";
}

function tipoDe(nombre: string): string {
  return TIPOS_POR_EXTENSION[extensionDe(nombre)] ?? "text/plain";
}

export const memoriaVacia = (): DocMemoria => ({
  evaluadas: [],
  aplicadas: {},
  pendientes: {},
});

/** Sube el documento al bucket privado del usuario (1 por conversación, sobrescribe). */
export async function guardarDocEnStorage(
  userId: string,
  convId: string,
  archivo: File,
): Promise<string | null> {
  if (!supabase) return null;
  const path = `${userId}/${convId}.${extensionDe(archivo.name)}`;
  const { error } = await supabase.storage
    .from(BUCKET)
    .upload(path, archivo, { upsert: true, contentType: archivo.type || tipoDe(archivo.name) });
  if (error) {
    console.warn("[sesion] No se pudo guardar el documento en Storage:", error.message);
    return null;
  }
  return path;
}

/** El texto pegado se persiste como .txt para poder rehidratar el chat igual que un archivo. */
export async function guardarTextoEnStorage(
  userId: string,
  convId: string,
  texto: string,
  nombre: string,
): Promise<string | null> {
  const archivo = new File([texto], nombre.endsWith(".txt") ? nombre : `${nombre}.txt`, {
    type: "text/plain",
  });
  return guardarDocEnStorage(userId, convId, archivo);
}

/** Guarda/actualiza la metadata del documento en la fila de la conversación. */
export async function guardarDocEnConversacion(
  convId: string,
  info: DocumentoInfo,
  storagePath: string | null,
  memoria: DocMemoria,
): Promise<void> {
  if (!supabase) return;
  await supabase
    .from("conversaciones")
    .update({
      doc_nombre: info.nombre,
      doc_hash: info.hash,
      doc_storage_path: storagePath,
      doc_toc: info.estructura_toc,
      doc_stats: info.stats,
      doc_memoria: memoria,
    })
    .eq("id", convId);
}

/** Actualiza solo la memoria (evaluadas / texto corregido) tras una revisión. */
export async function guardarMemoria(convId: string, memoria: DocMemoria): Promise<void> {
  if (!supabase) return;
  await supabase.from("conversaciones").update({ doc_memoria: memoria }).eq("id", convId);
}

/** Borra el documento de Storage (al subir una versión nueva o eliminar el chat). */
export async function borrarDocDeStorage(storagePath: string | null): Promise<void> {
  if (!supabase || !storagePath) return;
  await supabase.storage.from(BUCKET).remove([storagePath]);
}

const COLUMNAS_DOC = "doc_nombre, doc_hash, doc_storage_path, doc_toc, doc_stats, doc_memoria";

/** Lee la metadata del documento persistida en una conversación.
 *
 *  `doc_alcance` se pide aparte a propósito. Si esa columna no existe todavía
 *  (schema_v7.sql sin ejecutar), PostgREST falla la consulta ENTERA, no solo esa
 *  columna: pidiéndola junto al resto, un despliegue del frontend antes de la
 *  migración hacía que el chat perdiera el proyecto al reabrirlo y obligaba al
 *  estudiante a volver a subirlo. Así, como mucho, se pierde el alcance.
 */
export async function leerDocPersistido(convId: string): Promise<DocPersistido | null> {
  if (!supabase) return null;
  const { data } = await supabase
    .from("conversaciones")
    .select(COLUMNAS_DOC)
    .eq("id", convId)
    .single();
  if (!data || !data.doc_storage_path) return null;

  let alcance: AlcanceInfo | null = null;
  const { data: fila, error } = await supabase
    .from("conversaciones")
    .select("doc_alcance")
    .eq("id", convId)
    .single();
  if (error) {
    console.warn(
      "[sesion] No se pudo leer doc_alcance (¿falta ejecutar supabase/schema_v7.sql?). " +
        "El proyecto se restaura igual, pero el alcance vuelve al automático.",
    );
  } else if ((fila?.doc_alcance as AlcanceInfo)?.grupos?.length) {
    alcance = fila.doc_alcance as AlcanceInfo;
  }

  return {
    nombre: data.doc_nombre ?? "proyecto.pdf",
    hash: data.doc_hash ?? "",
    storagePath: data.doc_storage_path,
    toc: data.doc_toc ?? {},
    stats: data.doc_stats ?? [],
    memoria: (data.doc_memoria as DocMemoria) ?? memoriaVacia(),
    alcance,
  };
}

/** Guarda el alcance declarado para que sobreviva al cierre del chat. */
export async function guardarAlcance(convId: string, alcance: AlcanceInfo): Promise<void> {
  if (!supabase) return;
  const { error } = await supabase
    .from("conversaciones")
    .update({ doc_alcance: alcance })
    .eq("id", convId);
  if (error) {
    console.warn(
      "[sesion] No se pudo guardar el alcance (¿falta ejecutar supabase/schema_v7.sql?):",
      error.message,
    );
  }
}

/** Re-indexa el documento desde Storage y reaplica la memoria → DocumentoInfo vivo.
 *  Rúbrica y reglamento no viajan: son los oficiales UPAO, fijos en el backend. */
export async function rehidratar(persistido: DocPersistido): Promise<DocumentoInfo | null> {
  if (!supabase) return null;
  const { data, error } = await supabase.storage.from(BUCKET).download(persistido.storagePath);
  if (error || !data) {
    console.warn("[sesion] No se pudo descargar el documento para rehidratar:", error?.message);
    return null;
  }
  // El nombre debe conservar la extensión REAL de lo guardado: es lo que usa el
  // backend para elegir el extractor cuando la firma binaria no basta.
  const extensionGuardada = persistido.storagePath.split(".").pop() ?? "pdf";
  const nombre = persistido.nombre.toLowerCase().endsWith(`.${extensionGuardada}`)
    ? persistido.nombre
    : `${persistido.nombre}.${extensionGuardada}`;
  const archivo = new File([data], nombre, { type: tipoDe(nombre) });
  return subirDocumento(archivo, persistido.memoria);
}
