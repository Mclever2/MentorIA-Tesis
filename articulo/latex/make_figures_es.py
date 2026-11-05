"""Regenera las figuras del artículo en escala de grises (sin color) a partir de los
datos del Informe de Tesis v14 (Tablas 11-15, 25 y 27; Figura 8)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Nimbus Roman", "DejaVu Serif"],
    "font.size": 9, "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "legend.fontsize": 8, "axes.spines.top": False, "axes.spines.right": False,
    "savefig.dpi": 600, "figure.dpi": 100,
})

# ---------- Figure 1: mean quality in the common core per week (Table 27) ----------
weeks = ["Semana 4\nD1–D5", "Semana 5\nD1–D6", "Semana 6\nD1–D9", "Semana 7\nD1–D10", "Semana 9\nD1–D12"]
gc = [78.5, 79.7, 72.4, 77.2, 75.6]
ge = [71.2, 79.5, 83.6, 88.2, 83.9]
x = np.arange(len(weeks))
fig, ax = plt.subplots(figsize=(3.5, 2.5))
ax.plot(x, gc, color="0.45", linestyle="--", marker="s", markerfacecolor="white",
        markeredgecolor="0.25", markersize=5, linewidth=1.2, label="Grupo Control (n = 16)")
ax.plot(x, ge, color="black", linestyle="-", marker="o", markersize=5, linewidth=1.4,
        label="Grupo Experimental (n = 20)")
for xi, (a, b) in enumerate(zip(gc, ge)):
    ax.annotate(f"{a:.1f}", (xi, a), textcoords="offset points", xytext=(0, -11),
                ha="center", fontsize=7, color="0.3")
    ax.annotate(f"{b:.1f}", (xi, b), textcoords="offset points", xytext=(0, 5),
                ha="center", fontsize=7, color="black")
ax.set_xticks(x); ax.set_xticklabels(weeks)
ax.set_ylim(60, 95); ax.set_ylabel("Calidad en el núcleo común (%)")
ax.grid(axis="y", color="0.85", linewidth=0.5)
ax.legend(loc="lower right", frameon=False)
fig.tight_layout(); fig.savefig("../figuras/fig1_calidad_nucleo_comun.pdf"); fig.savefig("../figuras/fig1_calidad_nucleo_comun.png"); plt.close(fig)

# ---------- Figure 2: achievement by rubric dimension (Figure 8 of the thesis) ----------
dims = [f"D{i}" for i in range(1, 16)]
cols = ["W4", "W5", "W6", "W7", "W9"]
NA = np.nan
gc_v = np.array([
    [76, 80, 79, 81, 80], [62, 57, 58, 60, 59], [90, 91, 93, 85, 84], [100, 99, 100, 100, 100],
    [71, 81, 77, 82, 85], [67, 76, 73, 73, 73], [22, 56, 57, 74, 82], [82, 78, 79, 73, 74],
    [56, 60, 61, 75, 76], [100, 83, 83, 83, 86], [60, 47, 35, 43, 44], [14, 43, 29, 24, 32],
    [NA, 25, 25, 38, 56], [NA, 12, 25, 25, 31], [NA, 57, 57, 57, 57]], dtype=float)
gc_n = [[16]*5, [16]*5, [14, 14, 15, 16, 16], [15, 16, 16, 16, 16], [14, 15, 16, 16, 16],
        [13, 15, 16, 16, 16], [15]*5, [12, 13, 13, 15, 16], [1, 10, 10, 13, 16], [1, 3, 3, 13, 16],
        [1, 3, 4, 7, 10], [1, 3, 4, 7, 8], [None, 1, 1, 1, 2], [None, 1, 1, 1, 2], [None, 1, 1, 1, 2]]
ge_v = np.array([
    [72, 73, 77, 80, 79], [55, 71, 77, 84, 82], [67, 76, 76, 81, 83], [92, 96, 96, 97, 99],
    [79, 81, 86, 83, 82], [67, 76, 81, 85, 87], [83, 71, 84, 93, 92], [89, 89, 84, 91, 86],
    [78, 67, 90, 92, 92], [100, 100, 73, 84, 84], [40, 36, 44, 45, 65], [27, 34, 32, 39, 51],
    [NA, NA, 88, 88, 71], [NA, NA, 75, 75, 38], [NA, NA, 43, 43, 52]], dtype=float)
ge_n = [[20]*5, [18, 20, 20, 20, 20], [18, 20, 20, 20, 20], [18, 20, 19, 20, 20], [11, 20, 19, 20, 20],
        [5, 14, 19, 20, 20], [3, 8, 20, 20, 20], [3, 3, 19, 20, 20], [2, 3, 17, 20, 20], [2, 2, 13, 17, 20],
        [11, 11, 15, 15, 16], [8, 10, 14, 14, 16], [None, None, 1, 1, 7], [None, None, 1, 1, 8], [None, None, 1, 1, 6]]

fig, axes = plt.subplots(1, 2, figsize=(7.0, 5.2), sharey=True)
cmap = plt.get_cmap("Greys")
for ax, vals, ns, title in zip(axes, [gc_v, ge_v], [gc_n, ge_n], ["Grupo Control", "Grupo Experimental"]):
    masked = np.ma.masked_invalid(vals)
    im = ax.imshow(masked, cmap=cmap, vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(5)); ax.set_xticklabels(["Sem. 4", "Sem. 5", "Sem. 6", "Sem. 7", "Sem. 9"], fontsize=6.5)
    ax.set_yticks(range(15)); ax.set_yticklabels(dims)
    ax.set_title(title, fontsize=9)
    ax.tick_params(length=0)
    for s in ax.spines.values(): s.set_visible(False)
    for i in range(15):
        for j in range(5):
            v = vals[i, j]
            if np.isnan(v): continue
            color = "white" if v > 55 else "black"
            ax.text(j, i - 0.13, f"{int(v)}", ha="center", va="center", fontsize=6.5, color=color)
            ax.text(j, i + 0.25, f"(n={ns[i][j]})", ha="center", va="center", fontsize=5.2, color=color)
cbar = fig.colorbar(im, ax=axes, fraction=0.03, pad=0.02)
cbar.set_label("Criterios cumplidos entre los proyectos que redactaron la dimensión (%)", fontsize=8)
cbar.ax.tick_params(labelsize=7)
fig.savefig("../figuras/fig2_logro_por_dimension.pdf", bbox_inches="tight"); fig.savefig("../figuras/fig2_logro_por_dimension.png", bbox_inches="tight"); plt.close(fig)

# ---------- Figure 3: cumulative use vs. quality change (Tables 11, 15 and Figure 10) ----------
proj = ["E01","E02","E03","E04","E05","E06","E07","E08","E09","E10","E11","E12","E13","E14","E15","E16","E17","E18","E19","E20"]
queries = [3, 9, 12, 4, 0, 4, 4, 8, 16, 1, 43, 46, 22, 1, 0, 6, 6, 2, 24, 4]
q_s4 = [77.9, 72.0, 70.0, 50.0, 76.0, 61.3, 60.0, 41.2, 72.0, 73.3, 41.9, 87.1, 88.0, 60.9, 77.4, 75.3, 63.3, 50.0, 63.0, 74.4]
q_s9 = [90.9, 80.0, 93.3, 76.7, 100.0, 67.7, 60.0, 47.1, 92.0, 93.3, 74.4, 90.3, 88.0, 84.8, 71.0, 90.9, 75.5, 67.4, 71.7, 90.7]
change = [b - a for a, b in zip(q_s4, q_s9)]
assert sum(queries) == 215
fig, ax = plt.subplots(figsize=(3.5, 2.7))
ax.axhline(0, color="0.5", linewidth=0.8)
ax.scatter(queries, change, s=22, facecolor="black", edgecolor="black", zorder=3)
labels = {"E15": (1.5, -8.8), "E05": (-1.6, 26.0), "E14": (2.2, 22.0), "E04": (5.5, 27.5),
          "E03": (13.5, 24.3), "E09": (17.5, 21.0), "E10": (2.5, 19.0), "E18": (-1.2, 16.0),
          "E20": (5.3, 17.6), "E16": (7.3, 14.4), "E01": (-1.2, 12.0), "E17": (7.3, 11.0),
          "E02": (10.3, 8.6), "E08": (9.3, 4.3), "E06": (0.2, 4.6), "E07": (5.3, -2.2),
          "E13": (23.3, 1.0), "E19": (25.3, 9.7), "E11": (38.8, 33.2), "E12": (41.8, 4.2)}
for p, qx, cy in zip(proj, queries, change):
    lx, ly = labels[p]
    ax.text(lx, ly, p, fontsize=6, color="0.2", ha="left", va="center")
ax.set_xlabel("Consultas acumuladas al sistema, semanas 5 a 9")
ax.set_ylabel("Cambio de la calidad (puntos)")
ax.set_xlim(-2, 50); ax.set_ylim(-10, 36)
ax.grid(color="0.9", linewidth=0.5)
fig.tight_layout(); fig.savefig("../figuras/fig3_uso_vs_cambio.pdf"); fig.savefig("../figuras/fig3_uso_vs_cambio.png"); plt.close(fig)
print("changes:", [round(c, 1) for c in change])
print("OK")
