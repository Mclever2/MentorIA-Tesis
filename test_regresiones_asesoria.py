"""Regresiones (sin LLM) de la asesoría y la revisión completa.

Cada caso reproduce un fallo real visto al probar con los proyectos G1–G20:
    python test_regresiones_asesoria.py
"""

from api.intent import es_consulta_de_contenido, parte_pedido, separar_pegado
from api.metodologia import _anclar_objetivos_fases, _contar_elementos
from api.grafo import _cambios_con_bloque
from backend.graph.nodes.supervisor import _validar_decision_semantica

import re

# ── Fragmento pegado: el pedido es lo que va DESPUÉS del texto ────────────────
m = ("Mi título es: Sistema web para mejorar la gestión de inventarios en la empresa "
     "Distribuidora Norte SAC, Trujillo 2026. ¿Está bien planteado?")
assert separar_pegado(m) == ("Mi título es:", "¿Está bien planteado?")
assert parte_pedido(parte_pedido(m)) == parte_pedido(m), "parte_pedido debe ser idempotente"
assert es_consulta_de_contenido(m), "valorar un título pegado es una consulta, no un planteamiento"
assert separar_pegado("Mi problema es: ¿De qué manera X mejora Y? ¿Qué hipótesis podría plantear?")[1] \
    == "¿Qué hipótesis podría plantear?"
assert separar_pegado("¿Cuál es mi problema general?") is None
assert separar_pegado("Mi objetivo general es: Determinar X en Y. Mejóralo.")[1] == "Mejóralo."

# ── Objetivos del procedimiento: solo los del estudiante ─────────────────────
texto = """1.2.2. Objetivos específicos
● Identificar los esquemas de metadatos de las plataformas emisoras de activos tokenizados.
● Clasificar los esquemas de metadatos según su compatibilidad estructural.
● Aplicar los modelos de las cuatro señales de verificación sobre representaciones candidatas.
● Comparar el desempeño del sistema propuesto frente a un método sin inteligencia artificial,
mediante precisión, recall y F1-score.
1.3. Importancia del estudio
Texto que no es un objetivo."""
objetivos = _contar_elementos(texto, re.compile(r"objetivos?\s+espec[ií]fic", re.I))
assert len(objetivos) == 4, objetivos
fases = [
    {"fase": "Desarrollo", "objetivos_que_cubre": [
        "Aplicar los modelos de las cuatro señales de verificación",
        "Diseñar y desarrollar el prototipo funcional del sistema"]},        # inventado
    {"fase": "Evaluación", "actividades": "Calcular precisión, recall y F1-score y comparar con el método sin IA",
     "objetivos_que_cubre": ["Determinar la equivalencia entre representaciones digitales"]},
]
_anclar_objetivos_fases(fases, objetivos)
assert fases[0]["objetivos_que_cubre"] == [f"OE3: {' '.join(objetivos[2].split()[:14])}…"] or \
    fases[0]["objetivos_que_cubre"][0].startswith("OE3:"), fases[0]
assert len(fases[0]["objetivos_que_cubre"]) == 1, "el objetivo inventado no debe aparecer"
assert fases[1]["objetivos_que_cubre"][0].startswith("OE4:"), fases[1]

# ── Registro de cambios del núcleo: nada «aplicado» sin su bloque ─────────────
tm = "### Título del proyecto\nX\n### 2.3.1. Variable independiente\nY"
cambios = ("Título: Se incluyó la delimitación temporal.\n"
           "Objetivos: Se completó el tercer objetivo que estaba incompleto.\n"
           "Marco metodológico: Se recomienda desarrollar el procedimiento.")
filtrado = _cambios_con_bloque(cambios, tm)
assert "Objetivos" not in filtrado and "Título" in filtrado and "Marco metodológico" in filtrado
portada = _cambios_con_bloque(
    "Título: Se corrigió la línea de investigación a «Sistemas Inteligentes».\n"
    "Título: Se añadió el periodo 2026.", tm)
assert "línea" not in portada and "2026" in portada, portada
sin_etiqueta = _cambios_con_bloque(
    "Se completaron las hipótesis específicas que estaban truncadas.\n"
    "En el título, se agregó el periodo 2027.", tm)
assert "hipótesis" not in sin_etiqueta and "2027" in sin_etiqueta, sin_etiqueta

# ── Supervisor: no repite un nodo ya ejecutado en la iteración ───────────────
estado = {"numero_iteracion": 0, "max_iteraciones": 1, "errores_rubrica": [1],
          "auditor_ejecutado": True, "metodologo_ejecutado": True,
          "consenso_ejecutado": True, "disenso_ejecutado": True}
assert _validar_decision_semantica("consenso", estado), "consenso repetido debe rechazarse"
assert _validar_decision_semantica("disenso", estado)
assert _validar_decision_semantica("redactor", estado) is None

# ── Núcleo: sin citas que el estudiante no hizo ─────────────────────────────
from backend.graph.nodes.redactor import _sin_citas_ajenas

ctx = "Los desarrolladores omiten la normalización (Albarak y Bahsoon, 2018)."
out = _sin_citas_ajenas("✓ Ya cumple según Hernández et al. (2017). Degrada la calidad "
                        "(Albarak y Bahsoon, 2018).", ctx)
assert "Hernández" not in out and "Albarak y Bahsoon, 2018" in out, out

# ── Núcleo: el periodo del título sale del proyecto ──────────────────────────
from backend.graph.nodes.redactor import _anios_del_proyecto_en_titulo

nuc = "### Título del proyecto\nAplicación web de traducción en entornos académicos, 2024–2026\n\n### 1.2 Objetivos\nEn 2024."
res = _anios_del_proyecto_en_titulo(nuc, "Problema observado durante 2026 en la empresa.")
assert "[periodo por definir]" in res and "En 2024." in res, res      # solo toca el título
res = _anios_del_proyecto_en_titulo("### Título del proyecto\nSistema X en FEIMI, 2027", "segundo bimestre 2027")
assert res.endswith("2027"), res

print("OK — regresiones de asesoría y revisión completa")
