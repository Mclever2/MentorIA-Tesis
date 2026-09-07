"""
Reglas duras del marco metodológico y de la operacionalización.

Van aparte de los prompts porque son verificables: el tamaño de muestra se
calcula, no se opina, y el reparto entre lo que necesita validación de expertos
y lo que no depende de una distinción objetiva (si la métrica la produce el
sistema o la produce una persona).

Fuente de la estructura: la Tabla 9 de «Metodología de la Investigación — Guía
para el Proyecto de Tesis», uno de los libros indexados, más lo observado en los
11 proyectos REP_ISIA aprobados de la escuela.
"""

from __future__ import annotations

import math

# Columnas canónicas de la tabla de operacionalización (Tabla 9 del libro).
COLUMNAS_OPERACIONALIZACION = [
    "Variable",
    "Definición conceptual",
    "Definición operacional",
    "Dimensiones",
    "Indicadores",
    "Escala de medición",
]

# Parámetros estándar del cálculo muestral.
NIVEL_CONFIANZA_ESTANDAR = 95.0
MARGEN_ERROR_ESTANDAR = 5.0
MARGEN_ERROR_MAXIMO = 10.0

# z para los niveles de confianza que se usan en la práctica.
_Z = {90.0: 1.645, 95.0: 1.96, 97.0: 2.17, 99.0: 2.576}


def z_para(confianza: float) -> float:
    """Valor z de la normal para el nivel de confianza pedido."""
    if confianza in _Z:
        return _Z[confianza]
    # Aproximación de Acklam para el cuantil normal, por si piden otro nivel.
    p = 1 - (1 - confianza / 100.0) / 2
    a = [-39.6968302866538, 220.946098424521, -275.928510446969,
         138.357751867269, -30.6647980661472, 2.50662827745924]
    b = [-54.4760987982241, 161.585836858041, -155.698979859887,
         66.8013118877197, -13.2806815528857]
    c = [-0.00778489400243029, -0.322396458041136, -2.40075827716184,
         -2.54973253934373, 4.37466414146497, 2.93816398269878]
    d = [0.00778469570904146, 0.32246712907004, 2.445134137143, 3.75440866190742]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def tamano_muestra(
    poblacion: int,
    confianza: float = NIVEL_CONFIANZA_ESTANDAR,
    margen_error: float = MARGEN_ERROR_ESTANDAR,
    proporcion: float = 0.5,
) -> dict:
    """Muestra para población FINITA, con la fórmula que se exige en la ficha.

              N · z² · p · q
        n = ────────────────────────
            e²·(N−1) + z²·p·q

    `proporcion` = 0.5 es el caso más conservador (máxima varianza), que es lo
    que se usa cuando no hay un estudio previo del que tomar p.

    Se devuelve el cálculo entero —no solo el número— porque en la sustentación
    piden justificar cada parámetro, y un `n` sin z, e y N no se puede defender.
    """
    if poblacion <= 0:
        raise ValueError("La población debe ser mayor que cero.")
    if not 0 < margen_error <= MARGEN_ERROR_MAXIMO:
        raise ValueError(
            f"El margen de error debe estar entre 0 y {MARGEN_ERROR_MAXIMO:.0f} %."
        )

    z = z_para(confianza)
    e = margen_error / 100.0
    p = proporcion
    q = 1 - p

    numerador = poblacion * (z ** 2) * p * q
    denominador = (e ** 2) * (poblacion - 1) + (z ** 2) * p * q
    n = numerador / denominador

    return {
        "poblacion": poblacion,
        "confianza": confianza,
        "z": round(z, 3),
        "margen_error": margen_error,
        "proporcion": p,
        "muestra": math.ceil(n),
        "muestra_exacta": round(n, 2),
        "formula": "n = (N · z² · p · q) / (e² · (N − 1) + z² · p · q)",
        "sustitucion": (
            f"n = ({poblacion} · {round(z,3)}² · {p} · {q}) / "
            f"({e}² · ({poblacion} − 1) + {round(z,3)}² · {p} · {q}) = {round(n, 2)} → {math.ceil(n)}"
        ),
        "censo_recomendado": poblacion <= 60,
    }


# ── Qué necesita validación de expertos y qué no ────────────────────────────

# Métricas que produce el propio sistema: su cálculo es determinista y su
# validez no la da un panel de expertos sino la definición matemática.
METRICAS_COMPUTACIONALES = {
    "exactitud", "accuracy", "precision", "precisión", "recall", "sensibilidad",
    "especificidad", "f1", "f1-score", "auc", "roc", "mape", "rmse", "mae", "mse",
    "r2", "r cuadrado", "kappa", "matriz de confusion", "matriz de confusión",
    "tiempo de respuesta", "latencia", "throughput", "tasa de error", "tasa de acierto",
    "tiempo de procesamiento", "tiempo de ejecucion", "tiempo de ejecución",
    "consumo", "watts", "kwh", "uso de cpu", "uso de memoria", "disponibilidad",
    "cobertura", "tasa de duplicidad", "tasa de fraude", "tiempo de consolidacion",
    "tiempo de consolidación",
}

# Instrumentos que recogen la percepción o el juicio de una persona: aquí sí hay
# que demostrar que el instrumento mide lo que dice medir.
INSTRUMENTOS_CON_PERSONAS = {
    "cuestionario", "encuesta", "entrevista", "escala", "likert", "test",
    "guia de observacion", "guía de observación", "focus group", "grupo focal",
    "lista de cotejo", "rubrica", "rúbrica",
}


def requiere_validacion_experta(indicador: str, instrumento: str = "") -> bool:
    """¿Este indicador necesita juicio de expertos?

    La distinción que casi nadie hace y que ahorra semanas de trabajo: una
    métrica que calcula el propio sistema (exactitud, MAPE, tiempo de respuesta)
    no se valida con un panel de expertos — su validez está en su definición
    matemática, y lo que se valida es que el procedimiento de medición sea
    correcto. En cambio, un cuestionario de satisfacción sí: mide una percepción,
    y hay que demostrar que mide lo que dice medir.
    """
    texto = f"{indicador} {instrumento}".lower()
    if any(m in texto for m in INSTRUMENTOS_CON_PERSONAS):
        return True
    return not any(m in texto for m in METRICAS_COMPUTACIONALES)


def bloque_validacion() -> str:
    """Explicación lista para el prompt y para la respuesta al estudiante."""
    return (
        "CUÁNTOS INDICADORES Y A QUÉ COSTO. Cada indicador arrastra un instrumento, y cada "
        "instrumento que recoja la opinión o el juicio de una persona hay que VALIDARLO por juicio "
        "de expertos (habitualmente 3 a 5, con su ficha de validación) y comprobar su confiabilidad "
        "(alfa de Cronbach para escalas). Eso son semanas. Tener muchas dimensiones no está mal, "
        "pero el estudiante tiene que saber lo que cuesta antes de comprometerse, y saber que puede "
        "buscar un instrumento YA VALIDADO en la literatura y citarlo, en vez de construir uno.\n"
        "LA EXCEPCIÓN IMPORTANTE: las métricas que calcula el propio sistema —exactitud, F1, MAPE, "
        "tiempo de respuesta, consumo en watts— NO necesitan juicio de expertos. Su validez está en "
        "su definición matemática; lo que se valida ahí es que el procedimiento de medición sea "
        "correcto (misma máquina, mismas condiciones, mismo periodo), no la métrica en sí. "
        "Confundir esto lleva a estudiantes a montar paneles de expertos para validar un cronómetro."
    )


# ── Matriz de consistencia ──────────────────────────────────────────────────

# Columnas de la matriz: cruza lo ya definido, no introduce nada nuevo.
COLUMNAS_MATRIZ = [
    "Problema específico",
    "Objetivo específico",
    "Hipótesis específica",
    "Variable",
    "Indicadores",
]


def verificar_matriz(
    preguntas: list[str],
    objetivos: list[str],
    hipotesis: list[str] | None = None,
    exige_hipotesis: bool = True,
) -> list[str]:
    """Comprueba que la matriz se pueda armar con lo que ya está definido.

    La matriz de consistencia no aporta contenido: coloca lo de las secciones
    anteriores y enseña que encaja. Por eso lo que aquí falla no es un problema
    de formato de la tabla — es que una sección previa está incompleta, y ese es
    el hallazgo que hay que devolverle al estudiante en vez de rellenar la celda.
    """
    hipotesis = hipotesis or []
    hallazgos: list[str] = []

    if not preguntas:
        hallazgos.append(
            "No hay preguntas específicas definidas: la matriz no se puede armar porque su primera "
            "columna sale de ahí. Redáctalas antes."
        )
    if not objetivos:
        hallazgos.append(
            "No hay objetivos específicos definidos. Cada uno sale de su pregunta específica, así "
            "que primero cierra las preguntas."
        )
    if preguntas and objetivos and len(preguntas) != len(objetivos):
        hallazgos.append(
            f"Tienes {len(preguntas)} pregunta(s) específica(s) y {len(objetivos)} objetivo(s): "
            "deben ser el mismo número y en el mismo orden, porque cada objetivo deriva de una "
            "pregunta. Si sobra un objetivo, le falta su pregunta; si sobra una pregunta, no la "
            "estás respondiendo con ningún objetivo."
        )
    if exige_hipotesis:
        if not hipotesis:
            hallazgos.append(
                "Tu enfoque exige hipótesis y no hay ninguna definida; la columna de hipótesis "
                "específicas quedaría vacía."
            )
        elif objetivos and len(hipotesis) != len(objetivos):
            hallazgos.append(
                f"Tienes {len(objetivos)} objetivo(s) específico(s) y {len(hipotesis)} hipótesis: "
                "en un estudio que las exige, cada objetivo específico debe tener la suya."
            )
    return hallazgos
