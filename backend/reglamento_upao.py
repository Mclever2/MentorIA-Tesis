"""
Reglamento institucional UPAO por defecto — fuente única.

El sistema ya no busca ni acepta reglamentos subidos por el estudiante: trabaja
siempre con el Reglamento de Investigación e Innovación de la UPAO. Este módulo
destila del documento oficial SOLO lo necesario para dos usos:

  1. PERFIL_AGENTES_UPAO → modula la conducta de los agentes evaluadores
     (se inyecta como `perfil_institucional` en el estado del grafo, igual que
     antes hacía el perfil destilado de un reglamento subido).
  2. REGLAMENTO_UPAO["puntos"] → lo que el ESTUDIANTE ve en la interfaz:
     identificación, vigencia y los puntos del reglamento que afectan su proyecto.

Documento fuente: "Reglamento de Investigación e Innovación", código INS-VIN-RG-04,
versión 01, aprobado por Resolución de Consejo Directivo N.° 154-2026-CD-UPAO.
"""

REGLAMENTO_UPAO: dict = {
    "titulo":     "Reglamento de Investigación e Innovación",
    "universidad": "Universidad Privada Antenor Orrego (UPAO)",
    "codigo":     "INS-VIN-RG-04",
    "version":    "01",
    "vigencia":   "27/05/2026",
    "resolucion": "Resolución de Consejo Directivo N.° 154-2026-CD-UPAO",
    "deroga":     "Reglamento de Investigación aprobado por Resolución N.° 54-2024-CD-UPAO",
    "nota_vigencia": (
        "Versión 01, vigente desde el 27/05/2026 (entra en vigencia con su aprobación "
        "por el Consejo Directivo). Integra en un solo documento el anterior Reglamento "
        "de Investigación y el de Emprendimiento e Innovación."
    ),
    # Puntos del reglamento que afectan directamente un proyecto de tesis.
    # Se muestran al estudiante con su referencia (artículo) para que pueda verificarlos.
    "puntos": [
        {"ref": "Art. 23",
         "texto": "Los proyectos y tesis de pregrado y posgrado se desarrollan preferentemente "
                  "en las líneas de investigación vigentes de la Universidad."},
        {"ref": "Art. 37.b",
         "texto": "Criterios de elaboración del proyecto: generar aportes al conocimiento, "
                  "estar vinculado a una línea de investigación y ser viable con los recursos "
                  "humanos, materiales y financieros disponibles."},
        {"ref": "Art. 37.f",
         "texto": "Tipos de proyecto admitidos: investigación básica o aplicada (cualitativa, "
                  "cuantitativa o mixta), desarrollo tecnológico (prototipos, sistemas, "
                  "software) e innovación (validación de soluciones en contextos reales)."},
        {"ref": "Art. 36",
         "texto": "Buenas prácticas obligatorias: objetividad en datos y resultados, integridad "
                  "científica, declaración de conflictos de interés y respeto a la propiedad "
                  "intelectual y a la normativa ética."},
        {"ref": "Art. 10 y 36.h",
         "texto": "El uso de inteligencia artificial generativa debe ser responsable, trazable y "
                  "declararse explícitamente cuando influya en el diseño, análisis o redacción "
                  "del trabajo."},
        {"ref": "Art. 70.a y 72.d",
         "texto": "Citar y referenciar correctamente TODAS las fuentes usadas, conforme a las "
                  "normas internacionales de citación; toda idea ajena debe atribuirse a su autor."},
        {"ref": "Art. 71.a",
         "texto": "Si la investigación involucra seres humanos, requiere aprobación (o exoneración) "
                  "de un Comité de Ética y consentimiento informado de los participantes; con "
                  "animales o biodiversidad aplican sus normativas específicas."},
        {"ref": "Art. 7 y 73",
         "texto": "Gestión responsable de los datos de investigación (principios FAIR) y "
                  "conservación de registros por al menos 5 años, incluidos los diálogos con "
                  "herramientas de IA usados en la investigación."},
        {"ref": "Art. 54",
         "texto": "Las tesis de pregrado y posgrado se registran y publican en el Repositorio "
                  "Institucional (acceso abierto, en línea con la Ley N.° 30035 y ALICIA)."},
        {"ref": "Art. 76",
         "texto": "Plagiar, falsificar o inventar datos en proyectos e informes de investigación "
                  "constituye falta grave y genera proceso disciplinario."},
    ],
}


# Perfil que modula la CONDUCTA de los agentes evaluadores. Contiene solo lo que el
# reglamento exige y que un evaluador puede verificar en el proyecto (sin trámites
# administrativos internos, incentivos docentes ni asuntos de gestión).
PERFIL_AGENTES_UPAO: str = """\
Evalúas un proyecto de tesis de la Universidad Privada Antenor Orrego (UPAO), Perú, \
bajo su Reglamento de Investigación e Innovación (INS-VIN-RG-04 v01, Resolución de \
Consejo Directivo N.° 154-2026-CD-UPAO, vigente desde el 27/05/2026).
- Rúbrica oficial UPAO: escala 0-3 por ítem (0=Insuficiente, 1=Regular, 2=Bueno, 3=Excelente).
- El estudio debe enmarcarse en una línea de investigación vigente de la UPAO (Art. 23) y \
generar un aporte al conocimiento, siendo viable con los recursos humanos, materiales y \
financieros previstos (Art. 37.b).
- Tipos admitidos (Art. 37.f): investigación básica o aplicada — cualitativa, cuantitativa \
o mixta —, desarrollo tecnológico (prototipos, sistemas, software) e innovación (validación \
en contextos reales). Verifica que el tipo/diseño declarado sea coherente con lo que el \
proyecto realmente hace.

Énfasis que debes priorizar al evaluar:
- Integridad científica (Art. 36): objetividad en la recolección y comunicación de datos; \
sin plagio, falsificación ni invención de datos (Art. 76, falta grave).
- Citación correcta y completa de TODAS las fuentes según normas internacionales \
(Harvard, Vancouver, APA, ISO) y correspondencia entre citas y referencias (Arts. 70.a, 72.d).
- Ética con sujetos de investigación (Art. 71): si involucra seres humanos, exige mención de \
comité de ética y consentimiento informado; con animales o biodiversidad, sus autorizaciones.
- Uso de IA generativa declarado y trazable cuando influya en diseño, análisis o redacción \
(Arts. 10 y 36.h); no lo penalices si está declarado, obsérvalo si es evidente y no se declara.
- Gestión de datos (Arts. 7 y 73): valora que el proyecto prevea cómo recolecta, procesa y \
resguarda sus datos (instrumentos, procedimiento, análisis).
- Redacción publicable: la tesis termina en el Repositorio Institucional de acceso abierto \
(Art. 54), por lo que la claridad y el rigor formal cuentan.
- Referencias bibliográficas en APA 7.ª edición como norma preferente del programa, salvo \
que el texto declare otra norma internacional admitida."""


def perfil_institucional_upao() -> str:
    """Texto que viaja como `perfil_institucional` en el estado del grafo."""
    return PERFIL_AGENTES_UPAO
