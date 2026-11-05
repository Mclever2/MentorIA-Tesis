# Manuscrito en formato IEEE (LaTeX)

Artículo maquetado con la clase `IEEEtran` (modo *journal*, dos columnas, sin color, figuras en
escala de grises), listo para enviar por ScholarOne como PDF.

- `main_es.tex` es el **manuscrito principal, en español**, con `babel` español (rótulos TABLA,
  Fig., Referencias, Resumen) y, como exigen las revistas IEEE bilingües, título, *abstract* e
  *index terms* también en inglés. Apto para IEEE-RITA e IEEE Latin America Transactions.
- `main.tex` es la misma versión **en inglés**, con la cabecera de IEEE Transactions on Learning
  Technologies, por si se decide traducir el envío.

## Archivos

| Archivo | Contenido |
|---|---|
| `main_es.tex` / `main_es.pdf` | Manuscrito en español (12 páginas). Usa las figuras en español de `../figuras/`. |
| `main.tex` | Manuscrito en inglés (título, resumen, *index terms*, IMRAD, conclusiones, agradecimientos, disponibilidad de datos, biografías). |
| `references.bib` | 39 referencias en BibTeX; se formatean con `IEEEtran.bst` (estilo numérico IEEE). |
| `figures/` | Tres figuras en PDF y PNG a 600 ppp, en escala de grises y con rótulos en inglés. |
| `make_figures.py` | Regenera las figuras a partir de los datos del informe de tesis (Tablas 11 a 15, 25 y 27; Figura 8). |
| `make_figures_es.py` | Misma generación con rótulos en español; escribe en `../figuras/` para la versión en español del artículo. |
| `main.pdf` | Última compilación (11 páginas). |

## Compilar

Requiere TeX Live con `IEEEtran`, `booktabs`, `multirow` e `hyperref` (en Debian/Ubuntu:
`texlive-latex-extra` y `texlive-publishers`), o bien Overleaf subiendo `main.tex`,
`references.bib` y la carpeta `figures/`.

```bash
latexmk -pdf main_es.tex   # español
latexmk -pdf main.tex      # inglés
```

Para regenerar las figuras (necesita `matplotlib`):

```bash
python3 make_figures.py      # inglés, en figures/
python3 make_figures_es.py   # español, en ../figuras/
```

## Si se cambia de revista

- **Springer (ETHE, IJAIED, Education and Information Technologies):** sustituir la clase por la
  plantilla Springer Nature (`sn-jnl.cls`, descargable desde la web de Springer), mantener el texto y
  cambiar `\bibliographystyle` por el estilo `sn-basic` o `sn-apa` que exija la revista.
- **Revistas en Word (ET&S, AJET, RIED, Pixel-Bit):** partir de `../articulo_imrad.md` (español) o
  exportar este manuscrito con `pandoc main.tex --bibliography=references.bib -o main.docx`.
