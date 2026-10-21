"""Forecast how many usable samples a candidate site will give, before collecting.

A deliberately plain model: standardised screening features, ridge regression, and three safeguards that make the
number honest. (1) It is validated by leaving out whole clusters of nearby sites, so a neighbour is never in both parts.
(2) The interval comes from the held-out errors, not from a formula. (3) A per-region correction is fitted inside
the validation, shrunk towards zero, and only kept in the shipped model if it helps held-out error.

No trained or pretrained model is involved; everything is a few lines of linear algebra that can be checked by hand.
"""
import math

import numpy as np
from scipy import stats

import splitsafety as SS

DEFAULT_FEATURES = ["land_frac", "clear_frac", "fire_days", "aai_site", "no2_contrast", "co_contrast"]
ALPHAS = (0.01, 0.1, 1.0, 3.0, 10.0, 30.0)
CLUSTER_KM = 150.0


def _col(rows, f):
    return np.array([float(r[f]) if r.get(f) is not None and _isnum(r.get(f)) else np.nan for r in rows])


def _isnum(v):
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def design(rows, features, fit=None):
    """Feature matrix with missing values replaced by the training median and fire days on a log scale.

    ``fit`` carries the medians of the training rows so that new rows are treated identically.
    """
    X = np.column_stack([_col(rows, f) for f in features]) if rows else np.empty((0, len(features)))
    X = np.array(X, dtype=float)
    for j, f in enumerate(features):
        if f == "fire_days":
            X[:, j] = np.log1p(np.clip(X[:, j], 0, None))
    if fit is None:
        med = np.nanmedian(X, axis=0) if len(X) else np.zeros(len(features))
        med = np.where(np.isfinite(med), med, 0.0)
        fit = {"median": med}
    for j in range(X.shape[1]):
        bad = ~np.isfinite(X[:, j])
        X[bad, j] = fit["median"][j]
    return X, fit


def clusters(rows, radius_km=CLUSTER_KM):
    """Cluster id per row: rows within ``radius_km`` of each other (directly or through others) share a cluster."""
    n = len(rows)
    dsu = SS._DSU(list(range(n)))
    for i in range(n):
        for j in range(i + 1, n):
            if SS.haversine_km((rows[i]["lat"], rows[i]["lon"]), (rows[j]["lat"], rows[j]["lon"])) < radius_km:
                dsu.union(i, j)
    roots = {}
    out = []
    for i in range(n):
        out.append(roots.setdefault(dsu.find(i), len(roots)))
    return np.array(out)


def ridge_fit(X, y, alpha):
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    Z = (X - mu) / sd
    ym = y.mean()
    A = Z.T @ Z + alpha * len(y) * np.eye(Z.shape[1])
    w = np.linalg.solve(A, Z.T @ (y - ym))
    return {"mu": mu, "sd": sd, "w": w, "b": ym, "alpha": alpha}


def ridge_predict(m, X):
    return ((X - m["mu"]) / m["sd"]) @ m["w"] + m["b"]


def _oof_multi(X, y, cl, alphas):
    """Leave-one-cluster-out predictions for several regularisation strengths at once.

    The features are standardised once on ``X`` and each fold is solved from sums with the fold's rows removed, so a
    validation with a hundred clusters costs a few hundred small solves.
    """
    n, p = X.shape
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    Z = (X - mu) / sd
    G, zs, zy, ys = Z.T @ Z, Z.sum(axis=0), Z.T @ y, float(y.sum())
    preds = {a: np.full(n, np.nan) for a in alphas}
    eye = np.eye(p)
    for idx in _folds(cl):
        nt = n - len(idx)
        Zf, yf = Z[idx], y[idx]
        if nt < 3:
            for a in alphas:
                preds[a][idx] = (ys - yf.sum()) / max(nt, 1) if nt else y.mean()
            continue
        m = (zs - Zf.sum(axis=0)) / nt
        ym = (ys - float(yf.sum())) / nt
        S = (G - Zf.T @ Zf) - nt * np.outer(m, m)
        r = (zy - Zf.T @ yf) - nt * m * ym
        for a in alphas:
            w = np.linalg.solve(S + a * nt * eye, r)
            preds[a][idx] = (Zf - m) @ w + ym
    return preds


def _oof(X, y, cl, alpha):
    """Leave-one-cluster-out predictions."""
    return _oof_multi(X, y, cl, (alpha,))[alpha]


def _bounds(y):
    """(0, 1) when every outcome is a share between 0 and 1, otherwise no bounds: a forecast of a share is kept inside
    the shares, a forecast of another number (a gas level, say) is left alone."""
    y = np.asarray(y, float)
    return (0.0, 1.0) if len(y) and y.min() >= 0 and y.max() <= 1 else (-np.inf, np.inf)


def _folds(cl):
    return [np.nonzero(cl == c)[0] for c in np.unique(cl)]


def _region_bias(regions, resid, k=3.0):
    """Mean residual per region, shrunk towards zero by n / (n + k)."""
    out = {}
    for r in set(regions):
        m = np.array([x == r for x in regions])
        n = int(m.sum())
        out[r] = float(resid[m].mean() * n / (n + k)) if n else 0.0
    return out


def _apply_bias(regions, pred, bias):
    return pred + np.array([bias.get(r, 0.0) for r in regions])


def select_alpha(X, y, cl, alphas=ALPHAS):
    preds = _oof_multi(X, y, cl, alphas)
    scores = {a: float(np.mean(np.abs(preds[a] - y))) for a in alphas}
    best = min(scores, key=scores.get)
    return best, scores


def validate(rows, features, target, cluster_km=CLUSTER_KM, alphas=ALPHAS, region_correction=True, interval=0.8):
    """Leave-cluster-out validation of the forecast of ``target`` (a column of ``rows`` between 0 and 1).

    Returns the held-out error against guessing the training mean, the rank correlation, the coverage of the interval,
    and the held-out predictions per site (so a figure can be drawn). The regularisation strength and the region
    correction are chosen inside each training part, never on the held-out cluster.
    """
    rows = [r for r in rows if _isnum(r.get(target))]
    n = len(rows)
    if n < 10:
        raise ValueError("Need at least 10 sites with an outcome to validate a forecast.")
    y = _col(rows, target)
    lo, hi = _bounds(y)
    cl = clusters(rows, cluster_km)
    regions = [r.get("region") or "unknown" for r in rows]
    pred = np.full(n, np.nan)
    base = np.full(n, np.nan)
    half = np.full(n, np.nan)
    chosen = []
    for idx in _folds(cl):
        tr = np.setdiff1d(np.arange(n), idx)
        Xtr, fit = design([rows[i] for i in tr], features)
        Xte, _ = design([rows[i] for i in idx], features, fit)
        ytr, cltr = y[tr], cl[tr]
        a, _ = select_alpha(Xtr, ytr, cltr, alphas)
        chosen.append(a)
        inner = _oof(Xtr, ytr, cltr, a)
        resid = ytr - inner
        model = ridge_fit(Xtr, ytr, a)
        p = ridge_predict(model, Xte)
        if region_correction:
            bias = _region_bias([regions[i] for i in tr], resid)
            p = _apply_bias([regions[i] for i in idx], p, bias)
            inner_c = _apply_bias([regions[i] for i in tr], inner, bias)
            resid = ytr - inner_c
        pred[idx] = np.clip(p, lo, hi)
        base[idx] = ytr.mean()
        half[idx] = float(np.quantile(np.abs(resid), interval))
    err = np.abs(pred - y)
    berr = np.abs(base - y)
    ss_res, ss_tot = float(((y - pred) ** 2).sum()), float(((y - base) ** 2).sum())
    rho = float(stats.spearmanr(pred, y)[0]) if np.ptp(pred) > 0 else float("nan")
    cover = float(np.mean((y >= pred - half) & (y <= pred + half)))
    warning = (f"Only {n} sites: the numbers below are rough and will move when a site is added or removed." if n < 30 else None)
    return {"target": target, "n_sites": n, "warning": warning, "n_clusters": int(len(np.unique(cl))), "cluster_km": cluster_km,
            "features": list(features), "interval": interval,
            "mae": round(float(err.mean()), 4), "mae_baseline": round(float(berr.mean()), 4),
            "skill": round(1 - float(err.mean()) / float(berr.mean()), 4) if berr.mean() > 0 else None,
            "r2": round(1 - ss_res / ss_tot, 4) if ss_tot > 0 else None, "spearman": round(rho, 4),
            "interval_coverage": round(cover, 3), "alpha_chosen": {str(a): chosen.count(a) for a in sorted(set(chosen))},
            "region_correction": bool(region_correction),
            "sites": [{"id": r["id"], "observed": round(float(y[i]), 4), "forecast": round(float(pred[i]), 4),
                       "low": round(float(max(lo, pred[i] - half[i])), 4), "high": round(float(min(hi, pred[i] + half[i])), 4)}
                      for i, r in enumerate(rows)]}


def compare_models(rows, features, target, cluster_km=CLUSTER_KM, region_correction=True):
    """Is a bigger model worth it? Held-out error of guessing the mean, of each number alone, and of all of them together.

    Every row of the table is scored with the same leave-cluster-out procedure as :func:`validate`.
    """
    base = validate(rows, features[:1], target, cluster_km, region_correction=False)
    out = [{"model": "Guess the training average", "features": [], "mae": base["mae_baseline"], "skill": 0.0}]
    for f in features:
        v = validate(rows, [f], target, cluster_km, region_correction=region_correction)
        out.append({"model": f"{f} alone", "features": [f], "mae": v["mae"], "skill": v["skill"], "spearman": v["spearman"]})
    if len(features) > 1:
        v = validate(rows, features, target, cluster_km, region_correction=region_correction)
        out.append({"model": "All numbers together", "features": list(features), "mae": v["mae"], "skill": v["skill"], "spearman": v["spearman"]})
    singles = [m for m in out if len(m["features"]) == 1]
    best_single = min(singles, key=lambda m: m["mae"]) if singles else None
    allm = out[-1] if len(features) > 1 else None
    reading = None
    if best_single and allm:
        d = best_single["mae"] - allm["mae"]
        reading = ("Using all the numbers helps only a little over the best single number" if d < 0.005 else
                   "Using all the numbers beats the best single number" if d > 0 else "The best single number does better than all of them together")
    return {"target": target, "n_sites": base["n_sites"], "models": out, "best_single": best_single["model"] if best_single else None, "reading": reading}


def effort_saved(rows, forecasts, windows_key="windows", ok_key="ok_windows", fractions=(0.05, 0.1, 0.2, 0.3)):
    """What dropping the sites with the lowest forecast would have saved.

    ``forecasts`` is ``{site_id: forecast}``. For each fraction of sites dropped, reports the share of collection windows
    saved and the share of usable samples lost. Dropping at random would save and lose the same share.
    """
    rs = [r for r in rows if r["id"] in forecasts and _isnum(r.get(windows_key)) and _isnum(r.get(ok_key))]
    rs.sort(key=lambda r: forecasts[r["id"]])
    tw = sum(float(r[windows_key]) for r in rs)
    tok = sum(float(r[ok_key]) for r in rs)
    out = []
    for f in fractions:
        k = int(round(f * len(rs)))
        d = rs[:k]
        w, o = sum(float(r[windows_key]) for r in d), sum(float(r[ok_key]) for r in d)
        out.append({"drop_share_of_sites": f, "sites_dropped": k, "windows_saved_share": round(w / tw, 4) if tw else None,
                    "samples_lost_share": round(o / tok, 4) if tok else None,
                    "windows_saved": int(w), "samples_lost": int(o)})
    return {"n_sites": len(rs), "total_windows": int(tw), "total_samples": int(tok), "rows": out,
            "note": "Dropping at random saves and loses the same share. A useful forecast saves more than it loses."}


def fit_final(rows, features, target, cluster_km=CLUSTER_KM, region_correction=True, interval=0.8, alphas=ALPHAS):
    """The shipped model: fitted on every site, with the interval and region corrections taken from held-out errors."""
    rows = [r for r in rows if _isnum(r.get(target))]
    y = _col(rows, target)
    lo, hi = _bounds(y)
    cl = clusters(rows, cluster_km)
    X, fit = design(rows, features)
    a, _ = select_alpha(X, y, cl, alphas)
    inner = _oof(X, y, cl, a)
    regions = [r.get("region") or "unknown" for r in rows]
    bias = _region_bias(regions, y - inner) if region_correction else {}
    resid = y - _apply_bias(regions, inner, bias)
    m = ridge_fit(X, y, a)
    return {"target": target, "features": list(features), "alpha": a, "n_sites": len(rows), "interval": interval,
            "half_width": round(float(np.quantile(np.abs(resid), interval)), 4),
            "median": [float(v) for v in fit["median"]], "mu": [float(v) for v in m["mu"]], "sd": [float(v) for v in m["sd"]],
            "bounds": [None if not np.isfinite(lo) else float(lo), None if not np.isfinite(hi) else float(hi)],
            "w": [float(v) for v in m["w"]], "b": float(m["b"]), "region_bias": {k: round(v, 4) for k, v in bias.items()},
            "importance": {f: round(float(w), 4) for f, w in zip(features, m["w"])},
            "note": "Validated by leaving out clusters of nearby sites. See the validation record for the error."}


def predict(model, row):
    """Forecast for one site (a dict with the model's features and, if known, its region)."""
    X, _ = design([row], model["features"], {"median": np.array(model["median"])})
    m = {"mu": np.array(model["mu"]), "sd": np.array(model["sd"]), "w": np.array(model["w"]), "b": model["b"]}
    p = float(ridge_predict(m, X)[0])
    adj = float(model["region_bias"].get(row.get("region") or "unknown", 0.0))
    lo, hi = (model.get("bounds") or [0.0, 1.0])
    lo = -np.inf if lo is None else lo
    hi = np.inf if hi is None else hi
    v = float(np.clip(p + adj, lo, hi))
    h = model["half_width"]
    missing = [f for f in model["features"] if not _isnum(row.get(f))]
    return {"forecast": round(v, 4), "low": round(max(lo, v - h), 4), "high": round(min(hi, v + h), 4), "region_adjustment": round(adj, 4),
            "missing_features": missing}
