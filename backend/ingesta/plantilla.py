"""
Texto de ejemplo del formato oficial UPAO que el estudiante no reemplazó.

El formato de proyecto de tesis trae, bajo cada encabezado, un párrafo de relleno
(«El texto expositivo es aquel texto que ofrece al lector…»), instrucciones
(«Las referencias preferentemente deben estar en ISO 690… (luego borrar)») y
tablas con datos de muestra (laptop, silla, celular…). El estudiante sube el
documento completo aunque solo haya escrito dos secciones, así que ese relleno
llegaba intacto al índice RAG y se trataba como SU contenido:

  · el selector de alcance marcaba los 7 grupos como «ya tienes avance»;
  · el conversador describía el relleno como «el problema central» del alumno;
  · la red calificaba el párrafo de ejemplo como una metodología inconsistente.

Verificado en los 19 proyectos de la facultad que usan el formato: el mismo
párrafo aparece en todos, en las secciones que aún no redactaron.

Aquí solo se RECONOCE el relleno. Qué hacer con él (quitarlo del contenido y
avisar al estudiante de qué secciones siguen sin redactar) lo decide
`backend.rag.estructura`.
"""

from __future__ import annotations

import re

_TILDES = {"a": "aáÁ", "e": "eéÉ", "i": "iíÍ", "o": "oóÓ", "u": "uúüÚÜ", "n": "nñÑ"}


def _patron(frase: str) -> str:
    """Regex tolerante a tildes, mayúsculas y saltos de línea del PDF."""
    partes = []
    for c in frase:
        if c.isspace():
            # El número de página puede caer en medio del párrafo al saltar de hoja.
            partes.append(r"\s+(?:\d{1,3}\s+)?")
        elif c.lower() in _TILDES:
            partes.append(f"[{c.lower()}{c.upper()}{_TILDES[c.lower()]}]")
        else:
            partes.append(re.escape(c))
    return "".join(partes)


# Frases de relleno e instrucciones del formato. Se buscan en cualquier punto del
# texto (el PDF las parte en varias líneas y a veces van pegadas al encabezado).
_FRASES = [
    "El texto expositivo es aquel texto que ofrece al lector una información explícita "
    "sobre un tema puntual, de manera objetiva, es decir, sin que medie en ningún momento "
    "la opinión del autor o sus posicionamientos.",
    "En consecuencia, tampoco necesita utilizar argumentaciones para convencer.",
    "Textos expositivos divulgativos.",
    "Son aquellos que están dirigidos a un público amplio, sin requerimientos previos "
    "especializados, y, por lo tanto, abordan temas de interés general, usualmente desde "
    "una perspectiva relativamente simple.",
    "Sus oraciones tienden a ser breves y fáciles de comprender, y su lenguaje es llano y accesible.",
    "Las referencias preferentemente deben estar en ISO 690, no obstante, puede utilizar "
    "cualquiera que esté aprobado en el reglamento de grados y títulos de la universidad, "
    "además, se recomienda un software de gestión de estas como Zotero o Mendeley (luego borrar).",
    "Título del proyecto de tesis (Solo con mayúscula la primera letra y los nombres propios, "
    "máximo 20 palabras y sin comillas)",
    "Redactar la línea o sublínea según corresponda",
    "Elaborado por los autores (la tabla es solo referencial).",
    "El proyecto es financiado por la universidad y por el (los) tesistas.",
    "Tabla 2. Matriz de consistencia de la investigación.",
    "Problema general Objetivo General Hipótesis general Variables",
    "Problemas específicos Objetivos específicos Hipótesis específicas",
    "Variable Definición conceptual Definición operacional Dimensiones Indicador Fuente:",
    "Tabla 1. Operacionalización de variables.",
    "Variable Definición conceptual Definición operacional Dimensiones Escala de Medición",
    # Fila de ejemplo de la tabla de operacionalización.
    "Gestión por procesos Es una metodología estructurada que permite a una organización "
    "mejorar sus procesos esenciales, con el objetivo de incrementar su eficacia y "
    "rendimiento en forma general (Harrington 1991)",
    "ACTIVIDADES Fecha Inicio Fecha Término",
    "Costo Unitario Deprec. Subtotal",
    "N° Servicio Cantidad Costo Unitario Subtotal",
    "Elija un elemento.",
    # Trozos sueltos del mismo párrafo: cuando el estudiante borró una parte, o un
    # salto de página lo partió, la frase completa ya no aparece entera.
    "explícita sobre un tema puntual, de manera objetiva, es decir, sin que medie en ningún "
    "momento la opinión del autor o sus posicionamientos.",
    "tampoco necesita utilizar argumentaciones para convencer.",
    "Son aquellos que están dirigidos a un público amplio",
    "sin requerimientos previos especializados, y, por lo tanto, abordan temas de interés "
    "general, usualmente desde una perspectiva relativamente simple.",
    "Sus oraciones tienden a ser breves y fáciles de comprender",
    "y su lenguaje es llano y accesible.",
    "Textos expositivos divulgativos",
]
# Restos del párrafo de relleno cuando el estudiante lo recortó a medias
# («● H1: El texto expositivo es aquel texto que ofrece al lector una…»).
_FRAGMENTOS = [
    r"[Ee]l\s+texto\s+expositivo\s+es\s+aquel\s+texto[^●\n]{0,260}?(?:posicionamientos\.|(?=\n\S)|$)",
]

# Líneas completas que solo existen en el formato: filas de ejemplo de las tablas
# de presupuesto y cronograma, y rótulos de columnas partidos letra a letra.
_LINEAS = [
    r"\d\s+Laptop\s+Core\s+I5\s+1\s+2500\.00\s+Si\s+625\.00",
    r"\d\s+Silla\s+de\s+metal\s+fija\s+1\s+99\.00\s+No\s+99\.00",
    r"\d\s+Celular\s+1\s+999\.00\s+si\s+249\.75",
    r"\d\s+Servicio\s+de\s+internet\s+3\s+60\.00\s+180\.00",
    r"\d\s+Servicio\s+de\s+telefon[ií]a\s+m[oó]vil\s+3\s+40\.00\s+120\.00",
    r"\d\s+Servicio\s+de\s+movilidad\s+10\s+10\.00\s+100\.00",
    r"N\s+Total\s+x+\.x+",
    r"-\s*X\s+(cuaderno\s+de\s+papel\s+bond|lapiceros|engrapador)\.?",
    r"-\s*Y\s+etc\.?",
    r"MARCAR\s+MODALIDAD\s*:?\s*P\s+SP\s+D",
    r"-\s*1\s+(tesista|asesor)\.?",
    r"[a-e]\.\s+(Planificaci[oó]n|Implementaci[oó]n|Colecta\s+de\s+datos|"
    r"An[aá]lisis\s+e\s+interpretaci[oó]n\s+de\s+datos|Elaboraci[oó]n\s+del\s+informe)",
    r"29/03/2025\s+23/06/2025",
    r"N°\s+Bien\s+Cantida\s*d?",
    r"T[ií]tulo\s+de\s+la\s+investigaci[oó]n",
    r"Variables?\s+I+",
    r"Variable\s+(in)?dependiente",
    # Rótulos vacíos que el formato deja para que el estudiante los complete: si la
    # línea es SOLO el rótulo, no hay nada escrito («Población: 120 usuarios» sí).
    r"[-●•]?\s*Justificaci[oó]n\s+(te[oó]rica|pr[aá]ctica|metodol[oó]gica|social)\s*:",
    r"(Indicadores\s+)?Metodolog[ií]a|Indicadores|(In)?dependiente|Enfoque\s*:|"
    r"Tipo\s+de\s+investigaci[oó]n\s*:|Dise[nñ]o\s+de\s+investigaci[oó]n\s*:|"
    r"Poblaci[oó]n\s*:|Muestra\s*:|Fuente\s*:(\s*Elaborado\s+por\s+los\s+autores\.?)?",
    r"[-●•]",
    r"[A-Za-zÁÉÍÓÚáéíóú]{1,3}",       # «Ind / epe / ndi / ent / e» de rótulos verticales
    r"\d{1,3}",                        # número de página suelto
]

_RE_FRASES = [re.compile(_patron(f)) for f in _FRASES] + [re.compile(f) for f in _FRAGMENTOS]
_RE_LINEA = re.compile(r"^\s*(?:" + "|".join(_LINEAS) + r")\s*$", re.I | re.M)
_RE_VINETA_VACIA = re.compile(r"^\s*[●•\-]?\s*(H\s*[\dgGiI]+\s*:)?\s*$", re.M)


def quitar_plantilla(texto: str) -> str:
    """Devuelve el texto sin el relleno ni las tablas de ejemplo del formato."""
    if not texto:
        return texto
    limpio = texto.replace("\r\n", "\n").replace("\r", "\n")
    for patron in _RE_FRASES:
        limpio = patron.sub(" ", limpio)
    limpio = _RE_LINEA.sub("", limpio)
    limpio = _RE_VINETA_VACIA.sub("", limpio)
    limpio = re.sub(r"[ \t]{2,}", " ", limpio)
    limpio = re.sub(r"\n\s*\n+", "\n", limpio)
    return limpio.strip()


def tiene_plantilla(texto: str) -> bool:
    return any(p.search(texto or "") for p in _RE_FRASES)


def letras_propias(texto: str, encabezado: str = "") -> int:
    """Letras que escribió el estudiante, sin contar el propio encabezado."""
    cuerpo = texto or ""
    if encabezado and cuerpo.lstrip().startswith(encabezado.strip()):
        cuerpo = cuerpo.lstrip()[len(encabezado.strip()):]
    return sum(1 for c in cuerpo if c.isalpha())
