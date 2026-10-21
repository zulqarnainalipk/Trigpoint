"""Figure 1 of the TrigPoint note, drawn from the results in results/ (placement_public_results.json and public_extras_results.json).

Usage: python make_figure1.py   (writes results/figure1.png and results/figure1.pdf)
"""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "results")

OI = {"black": "#000000", "orange": "#E69F00", "sky": "#56B4E9", "green": "#009E73", "blue": "#0072B2", "verm": "#D55E00", "purple": "#CC79A7"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.linewidth": 0.7, "axes.spines.top": False, "axes.spines.right": False,
                     "xtick.major.width": 0.7, "ytick.major.width": 0.7, "axes.titlesize": 9.5, "axes.titleweight": "bold", "axes.titlelocation": "left"})
fig, axs = plt.subplots(1, 3, figsize=(8.2, 3.5), dpi=300)

# (a) placement: picture sensitivity against label sensitivity, per site (thin) and median over sites (bold)
PLACEMENT = os.environ.get("PLACEMENT_RESULTS", "placement_public_results.json")
pdat = json.load(open(os.path.join(A, PLACEMENT)))
okp = {k: v for k, v in pdat["sites"].items() if "error" not in v}
ax = axs[0]
dist = [float(x) for x in pdat["distances"]]
d = [0.0] + dist
def per_site_kept(v):
    return [1.0] + [[x for x in v["by_distance"] if x["distance_km"] == dd][0]["median_retained"] for dd in dist]
mat = np.array([per_site_kept(v) for v in okp.values()], float)
for row in mat:
    ax.plot(d, row, "-", color="#999999", lw=0.5, alpha=0.5, zorder=1)
ax.plot(d, np.nanmedian(mat, axis=0), "-o", color=OI["black"], lw=1.8, ms=3.5, label="Facility-like pixels\nstill in view (median)", zorder=3)
styles = {"no2": ("--", "s", OI["verm"], "NO$_2$"), "ch4": ("--", "^", OI["blue"], "CH$_4$"), "aai": ("--", "D", OI["green"], "Aerosol index"), "co": ("--", "v", OI["purple"], "CO")}
for tname, (ls, mk, col, lab) in styles.items():
    cols = []
    for dd in dist:
        vals = []
        for v in okp.values():
            tv = (v.get("targets") or {}).get(tname)
            if tv and "rows" in tv:
                r = [x for x in tv["rows"] if x["distance_km"] == dd]
                if r:
                    vals.append(r[0]["change_over_spread"])
        cols.append(float(np.median(vals)) if vals else np.nan)
    ax.plot(d, [0.0] + cols, ls, marker=mk, color=col, lw=1.1, ms=3, label=lab, zorder=2)
ax.set_xlabel("Shift of the box (km)")
ax.set_ylabel("Facility in view (solid);\nlabel change / daily spread (dashed)")
ax.set_xticks(d)
ax.set_ylim(-0.03, 1.05)
ax.legend(frameon=False, fontsize=7.2, loc="center right", handlelength=2.2, borderaxespad=0.1)
ax.set_title(f"a  Placement ({len(okp)} sites)")

# (b) forecast on the 25 public sites
px = json.load(open(os.path.join(A, "public_extras_results.json")))
ax = axs[1]
s = px["forecast"]["sites_detail"]
ob = np.array([x["observed"] for x in s]); fo = np.array([x["forecast"] for x in s]); lo = np.array([x["low"] for x in s]); hi = np.array([x["high"] for x in s])
ax.plot([0, 1], [0, 1], color="#777777", lw=0.8, ls=":")
ax.hlines(ob, lo, hi, color=OI["sky"], lw=1.0, alpha=0.8)
ax.plot(fo, ob, "o", color=OI["blue"], ms=3.5, mew=0)
ax.set_xlabel("Forecast yield (held out)")
ax.set_ylabel("Observed yield")
ax.set_xlim(0, 1.02); ax.set_ylim(0, 1.02)
ax.set_title(f"b  Forecast ({len(s)} sites)")

# (c) registry positions against the verified centre, matched public sites
errs = sorted(d["registry_error_km"] for d in px["registry"]["detail"])
ax = axs[2]
ypos = np.arange(1, len(errs) + 1)
ax.axvline(1, color="#777777", lw=0.6, ls=":")
ax.axvline(5, color="#777777", lw=0.6, ls=":")
ax.plot(errs, ypos, "o", color=OI["blue"], ms=5)
ax.set_xscale("log"); ax.set_xlim(0.1, 10); ax.set_ylim(0, len(errs) + 1)
ax.set_xticks([0.1, 1, 10]); ax.set_xticklabels(["0.1", "1", "10"])
ax.set_yticks(ypos); ax.set_yticklabels([f"site {i}" for i in ypos], fontsize=7.5)
ax.set_xlabel("Registry error against verified centre (km)", fontsize=8.5)
ax.set_title(f"c  Registry ({len(errs)} of {px['n_sites']} sites)")

for a_ in axs:
    a_.set_box_aspect(1)
fig.tight_layout(w_pad=1.6)
fig.savefig(os.path.join(A, "figure1.png"), dpi=300, bbox_inches="tight", pad_inches=0.04)
fig.savefig(os.path.join(A, "figure1.pdf"), bbox_inches="tight", pad_inches=0.04)
print("ok")
