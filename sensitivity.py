"""Placement sensitivity: how much do the chip and the targets change when the box is shifted?

The study takes one picture of the surroundings (a "context chip" wider than the box by twice the largest shift),
cuts out the box at the original position and at shifted positions, and measures how much the content changes. The
targets (satellite gas columns) are handled the same way: their value over the label window is taken at each shifted
position and compared with the day-to-day spread at the original position.

Only simple arithmetic is used: no trained model.
"""
import math

import numpy as np

import imagery_tools as it

DISTANCES_KM = (1.0, 2.0, 5.0, 10.0)
BEARINGS_8 = (0, 45, 90, 135, 180, 225, 270, 315)
VIS = ("B4", "B3", "B2")
CMP_BANDS = ("B2", "B3", "B4", "B8", "B11", "B12")
KM_PER_DEG = 111.32


def offsets(distances=DISTANCES_KM, bearings=BEARINGS_8):
    """The shifts to try: ``[{"distance_km", "bearing", "de_km", "dn_km"}]`` (bearing clockwise from north)."""
    out = []
    for d in distances:
        for b in bearings:
            r = math.radians(b)
            out.append({"distance_km": float(d), "bearing": int(b), "de_km": round(d * math.sin(r), 6), "dn_km": round(d * math.cos(r), 6)})
    return out


def shifted_centre(lat, lon, de_km, dn_km):
    """Latitude and longitude after moving ``de_km`` east and ``dn_km`` north."""
    nlat = max(-90.0, min(90.0, lat + dn_km / KM_PER_DEG))
    nlon = lon + de_km / (KM_PER_DEG * max(math.cos(math.radians(lat)), 1e-6))
    return nlat, (nlon + 180.0) % 360.0 - 180.0                    # stay between -180 and 180 across the date line


def box_overlap_share(box_km, de_km, dn_km):
    """Share of the original box that the shifted box still covers (squares of equal size)."""
    return max(0.0, 1 - abs(de_km) / box_km) * max(0.0, 1 - abs(dn_km) / box_km)


def context_km_needed(box_km, max_shift_km):
    return box_km + 2 * max_shift_km


def crop(chip, context_km, box_km, de_km=0.0, dn_km=0.0):
    """The part of a context chip that a box of ``box_km`` shifted by (de, dn) would see, or None when it leaves the picture."""
    h, w = chip.shape
    px_km = context_km / w
    size = int(round(box_km / px_km))
    cx = w / 2 + de_km / px_km
    cy = h / 2 - dn_km / px_km
    r0, c0 = int(round(cy - size / 2)), int(round(cx - size / 2))
    r1, c1 = r0 + size, c0 + size
    if r0 < 0 or c0 < 0 or r1 > h or c1 > w or r1 - r0 < 4 or c1 - c0 < 4:
        return None
    sl = (slice(r0, r1), slice(c0, c1))
    return it.Chip({k: v[sl] for k, v in chip.bands.items()}, chip.scl[sl], chip.cldprb[sl], None, chip.crs, dict(chip.meta))


def _ncc(a, b):
    a = a - a.mean()
    b = b - b.mean()
    den = math.sqrt(float((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / den) if den > 0 else float("nan")


def chip_difference(a, b):
    """How different two crops are, over pixels that are valid in both.

    ``nrmse`` is the root mean squared difference of six bands divided by their spread in ``a`` (0 means identical; 1.4
    means unrelated). ``ncc`` is the correlation of the visible brightness (1 means the same picture).
    ``index_change`` is the absolute change of the box mean of three indices.
    """
    if a is None or b is None or a.shape != b.shape:
        return None
    ok = it.valid_mask(a) & it.valid_mask(b)
    n = int(ok.sum())
    if n < 25:
        return None
    errs = []
    for k in CMP_BANDS:
        va, vb = a.bands[k][ok].astype(float), b.bands[k][ok].astype(float)
        sd = va.std()
        if sd > 1e-9:
            errs.append(float(np.sqrt(np.mean((va - vb) ** 2)) / sd))
    bright = lambda c: np.mean([c.bands[k][ok].astype(float) for k in VIS], axis=0)
    out = {"n_px": n, "nrmse": round(float(np.mean(errs)), 4) if errs else None, "ncc": round(_ncc(bright(a), bright(b)), 4)}
    chg = {}
    for name in ("ndvi", "bsi", "hsfi"):
        ia = it.compute_index(name, a.bands)[ok].astype(float)
        ib = it.compute_index(name, b.bands)[ok].astype(float)
        chg[name] = round(float(abs(np.nanmean(ia) - np.nanmean(ib))), 4)
    out["index_change"] = chg
    return out


def facility_mask(chip, kind="built_up", percentile=90.0):
    """Pixels that look most like the facility signal (a simple index mask above a percentile), for the retained-signal measure."""
    v = it.valid_mask(chip)
    score, gate = it.MASK_KINDS[kind][1](chip.bands)
    if not v.any():
        return np.zeros(chip.shape, bool)
    thr = float(np.percentile(score[v], percentile))
    return (score >= thr) & gate & v


def retained_signal(context_chip, context_km, box_km, de_km, dn_km, mask=None, kind="built_up"):
    """Of the facility-like pixels in the original box, the share still inside the shifted box (``retained``), and how many
    facility-like pixels the shifted box holds compared with the original (``relative_signal``)."""
    m = facility_mask(context_chip, kind) if mask is None else mask
    h, w = m.shape
    px_km = context_km / w
    size = int(round(box_km / px_km))

    def window(de, dn):
        cx, cy = w / 2 + de / px_km, h / 2 - dn / px_km
        r0, c0 = int(round(cy - size / 2)), int(round(cx - size / 2))
        r1, c1 = r0 + size, c0 + size
        if r0 < 0 or c0 < 0 or r1 > h or c1 > w:
            return None
        return r0, r1, c0, c1

    o, s = window(0, 0), window(de_km, dn_km)
    if o is None or s is None:
        return None
    orig = m[o[0]:o[1], o[2]:o[3]].sum()
    if orig == 0:
        return None
    r0, r1 = max(o[0], s[0]), min(o[1], s[1])
    c0, c1 = max(o[2], s[2]), min(o[3], s[3])
    inter = m[r0:r1, c0:c1].sum() if r1 > r0 and c1 > c0 else 0
    return {"retained": round(float(inter / orig), 4), "relative_signal": round(float(m[s[0]:s[1], s[2]:s[3]].sum() / orig), 4)}


def placement_study(context_chip, context_km, box_km, distances=DISTANCES_KM, bearings=BEARINGS_8, natural_chip=None, kind="built_up"):
    """Measure the change of chip content for every shift.

    ``natural_chip`` is an optional second scene of the same context (another date); the change between the two dates at
    the original position is the natural variation a shift is compared with.
    """
    ctrl = crop(context_chip, context_km, box_km)
    if ctrl is None:
        raise ValueError("The context chip is too small for this box.")
    mask = facility_mask(context_chip, kind)
    natural = chip_difference(ctrl, crop(natural_chip, context_km, box_km)) if natural_chip is not None else None
    rows = []
    for o in offsets(distances, bearings):
        sub = crop(context_chip, context_km, box_km, o["de_km"], o["dn_km"])
        row = {**o, "box_overlap": round(box_overlap_share(box_km, o["de_km"], o["dn_km"]), 4), "inside_context": sub is not None}
        if sub is not None:
            row["change"] = chip_difference(ctrl, sub)
            row["signal"] = retained_signal(context_chip, context_km, box_km, o["de_km"], o["dn_km"], mask)
        rows.append(row)
    by = {}
    for d in sorted({r["distance_km"] for r in rows}):
        sel = [r for r in rows if r["distance_km"] == d]
        ok = [r for r in sel if r.get("change")]
        def med(f):
            v = [f(r) for r in ok if f(r) is not None and np.isfinite(f(r))]
            return round(float(np.median(v)), 4) if v else None
        by[d] = {"distance_km": d, "n_directions": len(sel), "n_inside": len(ok),
                 "median_nrmse": med(lambda r: r["change"]["nrmse"]), "median_ncc": med(lambda r: r["change"]["ncc"]),
                 "median_box_overlap": med(lambda r: r["box_overlap"]),
                 "median_retained": med(lambda r: (r.get("signal") or {}).get("retained")),
                 "share_missing_facility": round(float(np.mean([(r.get("signal") or {}).get("retained", 1.0) < 0.5 for r in ok])), 3) if ok else None}
    return {"box_km": box_km, "context_km": context_km, "kind": kind, "natural_change": natural, "rows": rows, "by_distance": list(by.values()),
            "note": "Compared at the resolution of the context chip. A shift that leaves the picture is skipped."}


def tolerance_km(by_distance, key="median_retained", threshold=0.5, below_is_bad=True):
    """The largest tested shift that still keeps ``key`` on the good side of ``threshold`` (0 when none does)."""
    best = 0.0
    for r in sorted(by_distance, key=lambda r: r["distance_km"]):
        v = r.get(key)
        if v is None:
            break
        good = v >= threshold if below_is_bad else v <= threshold
        if good:
            best = r["distance_km"]
        else:
            break
    return best


def tolerance_sweep(by_distance, key="median_retained", thresholds=(0.25, 0.5, 0.75), below_is_bad=True):
    """The tolerance for several thresholds, so the choice of threshold can be seen and is not hidden in one number."""
    return {str(t): tolerance_km(by_distance, key, t, below_is_bad) for t in thresholds}


# ------------------------------------------------------------------------------------------------------
# targets
# ------------------------------------------------------------------------------------------------------

def target_sensitivity(control, shifted, tol_ratio=0.25, sweep=(0.1, 0.25, 0.5)):
    """How a target changes when the label window is shifted.

    ``control`` is ``{target: {"mean", "sd", "n"}}`` at the original position (``sd`` is the day-to-day spread of the
    window mean, ``n`` the number of days). ``shifted`` is a list of
    ``{"distance_km", "bearing", "values": {target: mean}}``. For each target and distance, reports the median absolute
    change, that change in units of the day-to-day spread and of the standard error of the mean, and the share of
    shifts whose change exceeds twice the standard error. The tolerance is the largest distance whose median change
    stays within ``tol_ratio`` of the day-to-day spread.
    """
    out = {}
    for t, c in control.items():
        sd, n, m0 = c.get("sd"), c.get("n"), c.get("mean")
        if m0 is None or not sd or not n:
            out[t] = {"note": "not enough data at the original position"}
            continue
        se = sd / math.sqrt(n)
        rows = []
        for d in sorted({s["distance_km"] for s in shifted}):
            deltas = [abs(s["values"][t] - m0) for s in shifted if s["distance_km"] == d and s["values"].get(t) is not None and np.isfinite(s["values"][t])]
            if not deltas:
                continue
            md = float(np.median(deltas))
            rows.append({"distance_km": d, "n_shifts": len(deltas), "median_abs_change": round(md, 5), "change_over_spread": round(md / sd, 4),
                         "change_over_se": round(md / se, 3), "share_above_2se": round(float(np.mean([x > 2 * se for x in deltas])), 3)})
        def tol_for(ratio):
            tol = 0.0
            for r in rows:
                if r["change_over_spread"] <= ratio:
                    tol = r["distance_km"]
                else:
                    break
            return tol
        out[t] = {"mean": m0, "sd": sd, "n_days": n, "se": round(se, 6), "rows": rows, "tolerance_km": tol_for(tol_ratio), "tol_ratio": tol_ratio,
                  "tolerance_sweep": {str(r): tol_for(r) for r in sweep}}
    return out
