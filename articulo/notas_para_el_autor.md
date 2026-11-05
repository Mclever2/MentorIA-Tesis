# Notas para el autor sobre el borrador del artículo

Borrador construido a partir de **Informe de Tesis v14** (`Informe_de_Tesis_-_v14.docx`) siguiendo
`00_lineamientos_imrad.md`. Archivo principal: `articulo_imrad.md` (y su exportación `articulo_imrad.docx`).

## 1. Decisiones tomadas en el borrador

| Decisión | Elección | Motivo |
|---|---|---|
| Idioma | Español, con resumen y palabras clave también en inglés | La tesis está en español y aún no hay revista elegida; el abstract en inglés es exigencia casi universal. |
| Estilo de citas | APA 7 | Es el estilo de la tesis; se cambia a IEEE/Vancouver solo cuando se elija la revista. |
| Estructura | Título · Resumen · Palabras clave · 1 Introducción · 2 Materiales y métodos · 3 Resultados · 4 Discusión (con limitaciones y futuras investigaciones) · 5 Conclusiones · Agradecimientos · Declaraciones · Referencias · Material de soporte | Estructura exigida por el curso y por Codina (2022); la variante "Materiales y métodos" conviene porque hay dos sistemas de software que describir. |
| Resumen | Estructurado (Objetivo, Método, Resultados, Conclusión), unas 330 palabras | Muchas revistas Q3/Q4 de educación y tecnología lo piden así; si la revista fija 250 palabras, recortar el bloque de resultados. |
| Título | Delimitado con institución y periodo, como pide el curso | Alternativa más breve para revistas internacionales: "Sistemas multiagente basados en modelos de lenguaje y calidad metodológica de proyectos de tesis en ingeniería: un cuasiexperimento longitudinal". |
| Antecedentes | De los 15 del informe se citan 12 en la introducción y la discusión; se omitieron Järvelä et al. (2023), Zeng et al. (2025) y Al Azher et al. (2026) | Solo los directamente relacionados con el objeto y con las brechas, como indica el curso. |
| Tablas | 7 tablas condensadas (el informe tiene 33) | Se conservaron las que deciden hipótesis o describen el instrumento; las tablas por proyecto (Tablas 11 a 15 del informe) pasan a material de soporte. |
| Figuras | 3, tomadas tal cual del informe: Figura 11 (núcleo común por grupo), Figura 8 (logro por dimensión) y Figura 10 (uso frente a cambio) | Son las que sostienen la hipótesis general, la HE4 y la HE3. Se descartó la Figura 6 del informe porque sus etiquetas del eje x se solapan. |
| Nombres propios | Se omitieron los nombres de los expertos validadores y de los asesores entrevistados | Práctica habitual en artículos; en la tesis sí figuran. |
| Modelo del sistema de mentoría | No se nombra el proveedor ni el modelo de MentorIA en el texto | Ver discrepancia en la sección 3. |

Correspondencia entre el informe y el artículo:

| Informe de tesis (v14) | Artículo |
|---|---|
| Resumen / Abstract | Resumen / Abstract (reescritos en formato estructurado) |
| 1.1, 2.1, 2.3, 2.4 | Introducción, párrafos 1 y 2 |
| 3.2 Antecedentes y brechas de 6.1.4, 6.2.6, 6.3.4, 6.4.3, 6.5.5 | Introducción, párrafos 2 a 4 |
| 2.2 Objetivos; 4.2 y 4.3 Hipótesis | Introducción, último párrafo |
| 5.1, 5.3, 5.4 | 2.1 Diseño |
| 5.5 | 2.2 Población y muestra |
| 5.2 (TRL) + repositorio del sistema | 2.3 Intervención |
| 5.6.1 a 5.6.7 | 2.4 Instrumentos y medidas |
| 5.7, Tabla 10 | 2.5 Procedimiento |
| 5.8 | 2.6 Análisis de datos |
| 6.1 | 3.1 (Tabla 1 condensa Tablas 6 a 9) |
| 6.2.1 a 6.2.3 | 3.2 (Tabla 2 = Tabla 18 del informe) |
| 6.2.4 y 6.2.5 | 3.3 (Tabla 3 = Tabla 24) |
| 6.3 | 3.4 (Figura 3 = Figura 10) |
| 6.4 | 3.5 (Tabla 4 = Tabla 28; Figura 1 = Figura 11) |
| 6.5 | 3.6 (Tabla 5 condensa Tablas 29 y 30) |
| 6.6 | 3.7 (Tabla 6 = Tabla 32) |
| 6.x.4 Discusiones, 6.7 Síntesis de brechas, 2.5 Limitaciones | 4 Discusión (Tabla 7 condensa Tabla 33) |
| 7 Conclusiones, 8 Recomendaciones | 5 Conclusiones (numeradas por objetivo) y 4.2 Investigación futura |

## 2. Pendientes que solo el autor puede resolver

Están marcados en el archivo con comentarios `<!-- [AUTOR] ... -->` (no se ven en el .docx).

1. **Revista destino.** Define idioma final, estilo de citas, límite de palabras, formato de tablas y figuras y plantilla. Con la revista elegida, el siguiente paso es adaptar el borrador a su guía para autores y a su checklist.
2. **Autoría.** Confirmar el orden de autores, los ORCID de ambos tesistas (en la tesis están vacíos) y el correo institucional de correspondencia.
3. **Descripción de MentorIA.** La tesis v14 no describe la arquitectura del sistema de mentoría; el párrafo 2.3 se redactó a partir del repositorio. Confirmar los nombres de los agentes y, sobre todo, el modelo: la tesis dice que gpt-4o-mini es uno de los modelos que MentorIA emplea; el README del repositorio dice `llama-3.3-70b-versatile` vía Groq. Debe quedar un solo dato coherente en tesis, artículo y repositorio.
4. **Declaración de uso de IA generativa** en la redacción del manuscrito, si la revista la exige.
5. **Disponibilidad de datos y código.** Confirmar si el repositorio será público al enviar y dónde se depositarán los datos agregados (Zenodo, OSF, repositorio institucional).
6. **Figura de arquitectura (opcional).** Si la revista valora la descripción técnica, agregar un diagrama de la red de agentes de MentorIA y del panel evaluador; en la tesis no hay figura de ese tipo.
7. **Consentimiento y ética.** Verificar si la Facultad exige mencionar un comité de ética o número de aprobación.

## 3. Discrepancias detectadas en la tesis (conviene corregirlas antes de la versión final)

- **Secciones completas en la semana 4.** El apartado 5.5 dice 32 descripciones del problema (15 y 17) y 24 justificaciones (14 y 10); el apartado 6.5.1 y la Tabla 29 dicen 33 (16 y 17) y 25 (14 y 11). El artículo usa 33 y 25 (los datos de resultados).
- **Figura 6 del informe** (trayectoria de la calidad): las etiquetas del eje x se solapan ("Semana 4Semana 5Semana 6"). Regenerarla con las etiquetas rotadas o abreviadas.
- **Índice de elaboración de la justificación, semana 4.** El texto de 6.5.2 dice mediana 15.0 % (total) y la Tabla 30 dice 15.2 % en el Grupo Control y 10.0 % en el Experimental; es coherente, pero conviene indicar en la tabla que el "Total" incluye ambos grupos.
- **Modelo de MentorIA** (ver pendiente 3).
- El informe cita "Figura 1" para el esquema del diseño, pero el esquema está en texto; en el artículo se presentó como notación en línea.

## 4. Estado frente al checklist de `00_lineamientos_imrad.md`

- [x] Título, resumen y palabras clave en español e inglés.
- [x] Introducción con objeto, problema, implicancias, justificación, oportunidad, brechas, antecedentes pertinentes y objetivos e hipótesis.
- [x] Métodos con tipo y diseño, población y muestra, instrumentos con validez y confiabilidad, procedimiento, análisis en Python y descripción de los sistemas.
- [x] Resultados con párrafo introductorio por objetivo, tablas con nota al pie, figuras no decorativas, normalidad y pruebas de hipótesis.
- [x] Discusión con contraste por antecedente, declaración sobre el estado del arte, cierre de brechas por tipo de aporte y limitaciones.
- [x] Conclusiones por objetivo con implicancias; recomendaciones de investigación futura.
- [x] Agradecimientos y declaraciones (conflicto, financiamiento, consentimiento, IA, datos).
- [x] Referencias APA 7, solo las citadas (39 entradas; verificado que cada cita del texto tiene entrada y cada entrada se cita).
- [x] Material de soporte enumerado.
- [ ] Revista elegida y formato adaptado (pendiente 1).
- [ ] Extensión final dentro del límite de la revista.
