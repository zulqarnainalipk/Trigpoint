"""Split-safety checks: footprint-overlap groups, a split certificate, a domain-shift report and a
near-duplicate chip detector.

None of this needs a trained model. The overlap groups use geometry only, the shift report uses a population
stability index and a two-sample test, and the duplicate detector uses a perceptual hash, correlation and structural
similarity over the eight flips and rotations of a small preview.
"""
import hashlib
import json
import math
from datetime import date, datetime, timezone

import numpy as np
from scipy import ndimage, fft, stats

KM_PER_DEG = 111.32
DEFAULTS = {"label_km": 10.0, "bg_inner_km": 30.0, "bg_outer_km": 75.0, "min_split_km": 150.0}
FOLD_OF_ROLE = {"decoy": "test"}      # a decoy site sits on the test side of a split, so it counts as test when sides are compared
LEVELS = ("box", "label", "background", "ring")
LEVEL_TEXT = {
    "box": "the chip boxes overlap",
    "label": "the 10 km label windows overlap",
    "background": "one site's label window lies in the other's background ring, or the label windows overlap",
    "ring": "the background rings overlap (the same as the distance rule)",
}


def _active(sites):
    return [s for s in sites if not s.get("rejected")]


def fold(role, fold_map=None):
    """The side of a split a role belongs to (a decoy counts as test)."""
    return (FOLD_OF_ROLE if fold_map is None else fold_map).get(role, role)


def haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


def _offset_km(a, b):
    """East and north offset of b from a in km (flat-earth, good to well under 1% for the distances used here)."""
    mid = math.radians((a[0] + b[0]) / 2)
    dlon = (b[1] - a[1] + 180.0) % 360.0 - 180.0
    return dlon * math.cos(mid) * KM_PER_DEG, (b[0] - a[0]) * KM_PER_DEG


# ------------------------------------------------------------------------------------------------------
# overlap graph and groups
# ------------------------------------------------------------------------------------------------------

def relations(a, b, cfg=None):
    """Which footprints of two sites overlap. Returns a set of 'box', 'label', 'background', 'ring'."""
    c = {**DEFAULTS, **(cfg or {})}
    d = haversine_km(a["center"], b["center"])
    out = set()
    if d >= 2 * c["bg_outer_km"] + 1e-9:
        return out
    out.add("ring")
    dx, dy = _offset_km(a["center"], b["center"])
    half = (float(a.get("box_km", 0)) + float(b.get("box_km", 0))) / 2
    if abs(dx) < half and abs(dy) < half:
        out.add("box")
    if abs(dx) < c["label_km"] and abs(dy) < c["label_km"]:
        out.add("label")
    # the background ring of one site (an annulus from inner to outer radius) reaches the label window of the other
    reach = c["label_km"] / 2
    if c["bg_inner_km"] - reach < d < c["bg_outer_km"] + reach or "label" in out:
        out.add("background")
    return out


def overlap_graph(sites, cfg=None):
    """Every pair of active sites whose footprints overlap, with the relations that hold and the distance."""
    s = _active(sites)
    c = {**DEFAULTS, **(cfg or {})}
    if len(s) < 2:
        return []
    lat = np.radians([x["center"][0] for x in s])
    lon = np.radians([x["center"][1] for x in s])
    pairs = []
    reach = 2 * c["bg_outer_km"] + 1e-9
    for i in range(len(s) - 1):
        h = np.sin((lat[i + 1:] - lat[i]) / 2) ** 2 + math.cos(lat[i]) * np.cos(lat[i + 1:]) * np.sin((lon[i + 1:] - lon[i]) / 2) ** 2
        d = 2 * 6371.0 * np.arcsin(np.minimum(1.0, np.sqrt(h)))
        for k in np.nonzero(d < reach)[0]:
            j = i + 1 + int(k)
            rel = relations(s[i], s[j], c)
            if rel:
                pairs.append({"a": s[i]["id"], "b": s[j]["id"], "distance_km": round(float(d[k]), 2),
                              "relations": sorted(rel, key=LEVELS.index), "roles": sorted({fold(s[i].get("role", "?")), fold(s[j].get("role", "?"))})})
    return pairs


class _DSU:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def overlap_groups(sites, level="background", cfg=None, pairs=None, fold_map=None):
    """Group id per site: sites linked at ``level`` (or a stronger relation) share a group and so must share a fold.

    Returns ``{"level", "group_of": {site_id: gid}, "groups": [{"id", "members", "roles", "mixed_roles"}], ...}``.
    """
    if level not in LEVELS:
        raise ValueError(f"level must be one of {list(LEVELS)}")
    s = _active(sites)
    pairs = overlap_graph(s, cfg) if pairs is None else pairs
    index = {x["id"]: i for i, x in enumerate(s)}
    dsu = _DSU(list(index.values()))
    n_edges = 0
    for p in pairs:
        if level in p["relations"]:
            dsu.union(index[p["a"]], index[p["b"]])
            n_edges += 1
    members = {}
    for x in s:
        members.setdefault(dsu.find(index[x["id"]]), []).append(x)
    groups, group_of = [], {}
    for k, root in enumerate(sorted(members)):
        ms = members[root]
        gid = f"g{k + 1:03d}"
        roles = sorted({fold(m.get("role", "?"), fold_map) for m in ms})
        groups.append({"id": gid, "members": [m["id"] for m in ms], "size": len(ms), "roles": roles, "mixed_roles": len(roles) > 1})
        for m in ms:
            group_of[m["id"]] = gid
    return {"level": level, "meaning": LEVEL_TEXT[level], "n_sites": len(s), "n_pairs": n_edges, "n_groups": len(groups),
            "n_multi_site_groups": sum(1 for g in groups if g["size"] > 1),
            "n_mixed_role_groups": sum(1 for g in groups if g["mixed_roles"]),
            "group_of": group_of, "groups": groups}


def group_summary(sites, cfg=None):
    """Pairs, groups and mixed-role groups at each level, so the levels can be compared (and compared with the distance rule)."""
    pairs = overlap_graph(sites, cfg)
    out = {}
    for lv in LEVELS:
        g = overlap_groups(sites, lv, cfg, pairs)
        out[lv] = {k: g[k] for k in ("meaning", "n_pairs", "n_groups", "n_multi_site_groups", "n_mixed_role_groups")}
    return {"n_sites": len(_active(sites)), "levels": out, "pairs": pairs}


# ------------------------------------------------------------------------------------------------------
# spatial dependence
# ------------------------------------------------------------------------------------------------------

def semivariogram(points, values, edges=(0, 50, 150, 300, 600, 1200, 2500, 6000)):
    """Empirical semivariance of one value per site against distance.

    ``points`` are (lat, lon); ``values`` one number per point (NaN is skipped). Returns bins with the number of pairs
    and the semivariance, the sample variance (the plateau a variogram settles towards) and a note when a bin has
    too few pairs to trust.
    """
    pts = [(p, v) for p, v in zip(points, values) if v is not None and np.isfinite(v)]
    n = len(pts)
    if n < 3:
        return {"n_sites": n, "bins": [], "variance": None, "note": "Fewer than three sites with a value."}
    lat = np.radians([p[0][0] for p in pts])
    lon = np.radians([p[0][1] for p in pts])
    z = np.array([p[1] for p in pts], dtype=float)
    iu, ju = np.triu_indices(n, 1)
    h = np.sin((lat[ju] - lat[iu]) / 2) ** 2 + np.cos(lat[iu]) * np.cos(lat[ju]) * np.sin((lon[ju] - lon[iu]) / 2) ** 2
    d = 2 * 6371.0 * np.arcsin(np.minimum(1.0, np.sqrt(h)))
    g = 0.5 * (z[iu] - z[ju]) ** 2
    bins = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (d >= lo) & (d < hi)
        k = int(m.sum())
        bins.append({"from_km": lo, "to_km": hi, "pairs": k, "semivariance": round(float(g[m].mean()), 6) if k else None,
                     "reliable": k >= 10})
    var = float(np.var(z, ddof=1))
    nn = np.full(n, np.inf)
    full = np.zeros((n, n))
    full[iu, ju] = d
    full = full + full.T
    np.fill_diagonal(full, np.inf)
    nn = full.min(axis=1)
    return {"n_sites": n, "bins": bins, "variance": round(var, 6),
            "median_nearest_neighbour_km": round(float(np.median(nn)), 1),
            "share_with_neighbour_within_150_km": round(float((nn < 150).mean()), 3),
            "pairs_under_150_km": int((d < 150).sum()),
            "note": "Indicative only: bins with fewer than 10 pairs are marked not reliable."}


# ------------------------------------------------------------------------------------------------------
# domain shift
# ------------------------------------------------------------------------------------------------------

def psi(reference, other, bins=None, eps=1e-4):
    """Population stability index of ``other`` against ``reference`` (bins are quantiles of the reference).

    With few sites the index is biased upwards (about (bins - 1) times the sum of 1/n over both groups), so by default the
    number of bins is one per 20 sites of the smaller group, between 3 and 10.
    """
    a = np.asarray([x for x in reference if x is not None and np.isfinite(x)], float)
    b = np.asarray([x for x in other if x is not None and np.isfinite(x)], float)
    if len(a) < 5 or len(b) < 5:
        return None
    if bins is None:
        bins = int(min(10, max(3, min(len(a), len(b)) // 20)))
    edges = np.unique(np.quantile(a, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0 if np.allclose(a.mean(), b.mean()) else None
    edges[0], edges[-1] = -np.inf, np.inf
    pa = np.histogram(a, edges)[0] / len(a)
    pb = np.histogram(b, edges)[0] / len(b)
    pa, pb = np.maximum(pa, eps), np.maximum(pb, eps)
    return float(np.sum((pb - pa) * np.log(pb / pa)))


def psi_level(v):
    if v is None:
        return "not enough data"
    return "small" if v < 0.1 else "moderate" if v < 0.25 else "large"


def domain_shift(rows, features, role_a="train", role_b="test", role_key="role"):
    """Compare the features of the sites in two roles. ``rows`` are dicts with the role and the feature values."""
    A = [r for r in rows if r.get(role_key) == role_a]
    B = [r for r in rows if r.get(role_key) == role_b]
    out = []
    for f in features:
        va = [r.get(f) for r in A if _finite(r.get(f))]
        vb = [r.get(f) for r in B if _finite(r.get(f))]
        entry = {"feature": f, "n_a": len(va), "n_b": len(vb)}
        if len(va) >= 5 and len(vb) >= 5:
            ks = stats.ks_2samp(va, vb)
            p = psi(va, vb)
            entry.update({"mean_a": round(float(np.mean(va)), 4), "mean_b": round(float(np.mean(vb)), 4), "psi": round(p, 4) if p is not None else None,
                          "psi_level": psi_level(p), "ks": round(float(ks.statistic), 4), "p_value": round(float(ks.pvalue), 5)})
        else:
            entry.update({"psi": None, "psi_level": "not enough data", "ks": None, "p_value": None})
        out.append(entry)
    ranked = sorted(out, key=lambda e: -(e["psi"] if e["psi"] is not None else -1))
    vals = [e["psi"] for e in ranked if e["psi"] is not None]
    return {"role_a": role_a, "role_b": role_b, "n_a": len(A), "n_b": len(B), "features": ranked,
            "median_psi": round(float(np.median(vals)), 4) if vals else None,
            "max_psi": round(float(max(vals)), 4) if vals else None,
            "n_large": sum(1 for v in vals if v >= 0.25),
            "most_different": [e["feature"] for e in ranked[:3] if e["psi"] is not None and e["psi"] >= 0.1]}


def _finite(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def shift_against_random(rows, features, role_a="train", role_b="test", n_perm=200, seed=0, role_key="role"):
    """Is the shift between the two roles larger than a random split of the same sizes would give?

    Returns the observed median PSI, the median PSI of ``n_perm`` random splits (mean and 95th percentile) and a
    permutation p-value. A region split shows a large shift; a random split shows a small one.
    """
    pool = [r for r in rows if r.get(role_key) in (role_a, role_b)]
    obs = domain_shift(pool, features, role_a, role_b, role_key)["median_psi"]
    if obs is None:
        return {"observed_median_psi": None, "note": "Not enough sites with values."}
    rng = np.random.default_rng(seed)
    n_a = sum(1 for r in pool if r.get(role_key) == role_a)
    nulls = []
    for _ in range(n_perm):
        perm = rng.permutation(len(pool))
        shuffled = [dict(pool[i], **{role_key: role_a if k < n_a else role_b}) for k, i in enumerate(perm)]
        m = domain_shift(shuffled, features, role_a, role_b, role_key)["median_psi"]
        if m is not None:
            nulls.append(m)
    nulls = np.array(nulls)
    return {"observed_median_psi": obs, "random_split_median_psi_mean": round(float(nulls.mean()), 4),
            "random_split_median_psi_p95": round(float(np.quantile(nulls, 0.95)), 4), "n_permutations": int(len(nulls)),
            "p_value": round(float((1 + (nulls >= obs).sum()) / (1 + len(nulls))), 4)}


# ------------------------------------------------------------------------------------------------------
# near-duplicate chips
# ------------------------------------------------------------------------------------------------------

TRANSFORMS = [
    ("identity", lambda a: a), ("flip left-right", lambda a: a[:, ::-1]), ("flip up-down", lambda a: a[::-1, :]),
    ("rotate 90", lambda a: np.rot90(a, 1)), ("rotate 180", lambda a: np.rot90(a, 2)), ("rotate 270", lambda a: np.rot90(a, 3)),
    ("transpose", lambda a: a.T), ("anti-transpose", lambda a: np.rot90(a, 2).T),
]
SIZE = 32


def small(a, n=SIZE):
    """Area-average a 2-D image down to n by n (NaN filled with the median first)."""
    a = np.asarray(a, dtype=float)
    a = np.where(np.isfinite(a), a, np.nanmedian(a) if np.isfinite(a).any() else 0.0)
    h, w = a.shape
    if h == n and w == n:
        return a
    ys = np.linspace(0, h, n + 1).astype(int)
    xs = np.linspace(0, w, n + 1).astype(int)
    csum = np.pad(a.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    tot = csum[np.ix_(ys[1:], xs[1:])] - csum[np.ix_(ys[:-1], xs[1:])] - csum[np.ix_(ys[1:], xs[:-1])] + csum[np.ix_(ys[:-1], xs[:-1])]
    area = np.outer(np.diff(ys), np.diff(xs)).astype(float)
    return tot / np.maximum(area, 1)


def phash(a):
    """63-bit perceptual hash: low-frequency DCT coefficients of a 32 by 32 preview against their median."""
    c = fft.dctn(small(a), norm="ortho")[:8, :8].ravel()[1:]
    return c > np.median(c)


def hist_match(src, ref):
    """Map the values of ``src`` onto the distribution of ``ref`` by rank, so brightness and colour changes cancel."""
    s = src.ravel()
    order = np.argsort(s, kind="stable")
    out = np.empty_like(s)
    out[order] = np.sort(ref.ravel())
    return out.reshape(src.shape)


def ncc(a, b):
    a = a - a.mean()
    b = b - b.mean()
    den = math.sqrt(float((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / den) if den > 0 else 0.0


def ssim(a, b, win=7):
    """Mean structural similarity of two images already on the same scale (data range from the images)."""
    rng = float(max(a.max(), b.max()) - min(a.min(), b.min())) or 1.0
    c1, c2 = (0.01 * rng) ** 2, (0.03 * rng) ** 2
    f = lambda x: ndimage.uniform_filter(x, win, mode="reflect")
    ma, mb = f(a), f(b)
    va, vb, cab = f(a * a) - ma * ma, f(b * b) - mb * mb, f(a * b) - ma * mb
    s = ((2 * ma * mb + c1) * (2 * cab + c2)) / ((ma * ma + mb * mb + c1) * (va + vb + c2))
    return float(s.mean())


def _score(x, y):
    m = hist_match(x, y)
    return ncc(m, y), m


def compare_pair(a, b, max_shift=1):
    """Best match of preview ``a`` against ``b`` over the eight flips and rotations and small shifts.

    First every orientation is scored without a shift; the best orientation is then tried with small shifts. Returns
    the transform name, the shift, the Hamming distance of the hashes, and the correlation and structural similarity
    after histogram matching.
    """
    sa, sb = small(a), small(b)
    hb = phash(sb)
    best = None
    for name, fn in TRANSFORMS:
        ta = np.ascontiguousarray(fn(sa))
        c, m = _score(ta, sb)
        if best is None or c > best["ncc"]:
            best = {"transform": name, "shift": [0, 0], "hamming": int((phash(ta) != hb).sum()), "ncc": c, "_t": ta, "_x": m, "_y": sb}
    ta = best["_t"]
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            if not (dy or dx):
                continue
            sl = (slice(max(dy, 0), SIZE + min(dy, 0)), slice(max(dx, 0), SIZE + min(dx, 0)))
            sl2 = (slice(max(-dy, 0), SIZE + min(-dy, 0)), slice(max(-dx, 0), SIZE + min(-dx, 0)))
            x, y = ta[sl2], sb[sl]
            c, m = _score(x, y)
            if c > best["ncc"]:
                best.update({"shift": [dy, dx], "ncc": c, "_x": m, "_y": y})
    best.pop("_t")
    best["ncc"] = round(best["ncc"], 4)
    best["ssim"] = round(ssim(best.pop("_x"), best.pop("_y")), 4)
    return best


DUP_RULE = {"ncc_min": 0.85, "ssim_min": 0.75}


def _rank_unit(a):
    r = stats.rankdata(a.ravel()).astype(float)
    r -= r.mean()
    n = np.linalg.norm(r)
    return r / n if n > 0 else r


def near_duplicates(images, rule=None, candidate_min=0.5, max_shift=1, pair_filter=None):
    """Find pairs of images that are flipped, rotated, shifted or recoloured copies of each other.

    Stage one is a fast screen: the rank correlation (which ignores any monotone change of brightness or colour) between
    every image and all eight flips and rotations of every other, done as one matrix product. Pairs above
    ``candidate_min`` go to stage two (:func:`compare_pair`: small shifts, histogram matching, correlation and structural
    similarity). A pair is a near-duplicate when both exceed the rule. ``pair_filter(a, b)`` can return False for pairs that
    should not be examined (for example two dates of the same site).
    """
    r = {**DUP_RULE, **(rule or {})}
    ids = list(images)
    n = len(ids)
    prev = {i: small(images[i]) for i in ids}
    if n < 2:
        return {"n_images": n, "n_pairs": 0, "pairs_examined": 0, "rule": r, "found": []}
    coarse = {i: small(prev[i], 12) for i in ids}                    # coarse enough that a shift of a pixel or two barely matters
    base = np.stack([_rank_unit(coarse[i]) for i in ids])
    variants = np.stack([[_rank_unit(np.ascontiguousarray(fn(coarse[i]))) for _name, fn in TRANSFORMS] for i in ids])
    corr = np.einsum("ik,jtk->ijt", base, variants).max(axis=2)                          # n x n
    both = np.maximum(corr, corr.T)
    xs, ys = np.nonzero(np.triu(both >= candidate_min, 1))
    order = np.argsort(-both[xs, ys], kind="stable")                                     # most alike first
    found, examined = [], 0
    for k in order:
        x, y = int(xs[k]), int(ys[k])
        if pair_filter is not None and not pair_filter(ids[x], ids[y]):
            continue
        examined += 1
        res = compare_pair(prev[ids[x]], prev[ids[y]], max_shift)
        if res["ncc"] >= r["ncc_min"] and res["ssim"] >= r["ssim_min"]:
            found.append({"a": ids[x], "b": ids[y], **res, "verdict": "near_duplicate"})
    found.sort(key=lambda p: -p["ncc"])
    return {"n_images": n, "n_pairs": n * (n - 1) // 2, "pairs_examined": examined, "rule": r, "found": found}


def chip_preview(chip):
    """A grey preview for duplicate detection: the mean of the visible bands (empty pixels filled)."""
    vis = np.stack([chip.bands[b] for b in ("B4", "B3", "B2")]).astype(float)
    g = np.nanmean(vis, axis=0)
    return small(g)


# ---------- synthetic benchmark ----------

def _field(rng, n=96):
    """A terrain-like test picture: smooth noise at three scales plus a few sharp rectangles."""
    f = sum(ndimage.gaussian_filter(rng.normal(size=(n, n)), s) * w for s, w in ((1.5, 1.0), (4, 2.5), (10, 6.0)))
    for _ in range(int(rng.integers(3, 7))):
        y, x = rng.integers(5, n - 20, size=2)
        h, w = rng.integers(4, 16, size=2)
        f[y:y + h, x:x + w] += rng.uniform(-8, 8)
    return f


def _augment(img, kind, rng):
    n = img.shape[0]
    if kind in dict(TRANSFORMS):
        return dict(TRANSFORMS)[kind](img).copy()
    if kind == "shift 1-4 px":
        dy, dx = rng.integers(1, 5, size=2) * rng.choice([-1, 1], size=2)
        return np.roll(np.roll(img, int(dy), 0), int(dx), 1)
    if kind == "brightness and contrast":
        return img * rng.uniform(0.6, 1.5) + rng.uniform(-3, 3)
    if kind == "gamma (monotone recolour)":
        z = (img - img.min()) / (np.ptp(img) + 1e-9)
        return z ** rng.uniform(0.5, 2.0)
    if kind == "noise":
        return img + rng.normal(scale=0.25 * img.std(), size=img.shape)
    if kind == "flip + brightness + noise":
        return dict(TRANSFORMS)["flip left-right"](img) * rng.uniform(0.7, 1.3) + rng.normal(scale=0.15 * img.std(), size=img.shape)
    raise ValueError(kind)


AUGMENTATIONS = [n for n, _ in TRANSFORMS[1:]] + ["shift 1-4 px", "brightness and contrast", "gamma (monotone recolour)", "noise",
                                                   "flip + brightness + noise"]


def synthetic_benchmark(n_base=40, seed=0, rule=None, max_shift=1):
    """Detection rate for each kind of copy and the false-alarm rate among unrelated pictures.

    Builds ``n_base`` unrelated pictures, makes one copy of a few of them per augmentation, runs the detector on the whole
    set and counts. Everything is generated, so it can be repeated exactly.
    """
    rng = np.random.default_rng(seed)
    base = {f"base{i:03d}": _field(rng) for i in range(n_base)}
    per_kind = {}
    for kind in AUGMENTATIONS:
        picks = rng.choice(n_base, size=min(10, n_base), replace=False)
        imgs = dict(base)
        truth = set()
        for k in picks:
            cid = f"copy_{kind}_{k:03d}"
            imgs[cid] = _augment(base[f"base{k:03d}"], kind, rng)
            truth.add(frozenset((f"base{k:03d}", cid)))
        res = near_duplicates(imgs, rule, max_shift=max_shift)
        flagged = {frozenset((p["a"], p["b"])) for p in res["found"]}
        n_unrelated_pairs = res["n_pairs"] - len(truth)
        false = flagged - truth
        per_kind[kind] = {"copies": len(truth), "detected": len(truth & flagged), "rate": round(len(truth & flagged) / len(truth), 3),
                          "false_alarms": len(false), "unrelated_pairs": n_unrelated_pairs}
    total_false = sum(v["false_alarms"] for v in per_kind.values())
    total_pairs = sum(v["unrelated_pairs"] for v in per_kind.values())
    total_c = sum(v["copies"] for v in per_kind.values())
    total_d = sum(v["detected"] for v in per_kind.values())
    return {"seed": seed, "n_base": n_base, "per_kind": per_kind, "overall_detection_rate": round(total_d / total_c, 3),
            "false_alarm_rate": round(total_false / total_pairs, 6), "false_alarms": total_false, "unrelated_pairs_checked": total_pairs}


# ------------------------------------------------------------------------------------------------------
# certificate
# ------------------------------------------------------------------------------------------------------

def roster_hash(sites):
    canon = json.dumps([{"id": s["id"], "role": s.get("role"), "center": [round(float(s["center"][0]), 6), round(float(s["center"][1]), 6)],
                         "box_km": s.get("box_km")} for s in sorted(_active(sites), key=lambda x: x["id"])], sort_keys=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _min_distance_between_roles(sites, fold_map=None):
    s = [dict(x, role=fold(x.get("role"), fold_map)) for x in _active(sites)]
    roles = sorted({x.get("role") for x in s})
    out = {}
    for i, ra in enumerate(roles):
        for rb in roles[i + 1:]:
            A = [x for x in s if x.get("role") == ra]
            B = [x for x in s if x.get("role") == rb]
            best = None
            for a in A:
                for b in B:
                    d = haversine_km(a["center"], b["center"])
                    if best is None or d < best[0]:
                        best = (d, a["id"], b["id"])
            if best:
                out[f"{ra}|{rb}"] = {"km": round(best[0], 1), "a": best[1], "b": best[2]}
    return out


def _check(cid, title, status, value, detail):
    return {"id": cid, "title": title, "status": status, "value": value, "detail": detail}


def build_certificate(sites, cfg=None, tool_version="", targets=None, time_info=None, duplicates=None, shift=None,
                      features=None, rows=None):
    """One machine-readable record of whether a split is safe.

    ``targets`` is an optional ``{site_id: value}`` (one number per site, for example the site mean of a gas column) for
    the spatial dependence. ``time_info`` is an optional ``{"train_end": "YYYY-MM-DD", "test_start": "YYYY-MM-DD"}``.
    ``duplicates`` is the result of :func:`near_duplicates`; ``shift`` the result of :func:`domain_shift`.
    Checks that were not run say ``not_run`` and never count as passed.
    """
    c = {**DEFAULTS, **(cfg or {})}
    s = _active(sites)
    checks = []
    md = _min_distance_between_roles(s)
    cross = md
    if cross:
        worst = min(v["km"] for v in cross.values())
        st = "pass" if worst >= c["min_split_km"] else "fail"
        checks.append(_check("min_distance", "Closest sites in different roles", st, worst,
                             f"The closest pair across roles is {worst:g} km apart; the rule needs at least {c['min_split_km']:g} km."))
    else:
        checks.append(_check("min_distance", "Closest sites in different roles", "not_run", None, "Fewer than two roles in the roster."))
    pairs = overlap_graph(s, c)
    role_of = {x["id"]: fold(x.get("role")) for x in s}
    crossing = [p for p in pairs if role_of[p["a"]] != role_of[p["b"]]]
    for lv, title in (("box", "Chip boxes overlapping across roles"), ("label", "Label windows overlapping across roles"),
                      ("background", "Background rings reaching across roles"), ("ring", "Background rings overlapping across roles")):
        n = sum(1 for p in crossing if lv in p["relations"])
        checks.append(_check(f"overlap_{lv}", title, "pass" if n == 0 else "fail", n,
                             "None." if n == 0 else f"{n} pair(s) of sites in different roles; they should share a fold."))
    groups = overlap_groups(s, "ring", c, pairs)
    if time_info and time_info.get("train_end") and time_info.get("test_start"):
        try:
            gap = (date.fromisoformat(time_info["test_start"]) - date.fromisoformat(time_info["train_end"])).days
            checks.append(_check("time_gap", "Time between the training and test periods", "pass" if gap >= 0 else "fail", gap,
                                 f"The test period starts {gap} day(s) after the training period ends." if gap >= 0 else
                                 "The periods overlap."))
        except ValueError:
            checks.append(_check("time_gap", "Time between the training and test periods", "not_run", None, "Dates must be YYYY-MM-DD."))
    else:
        checks.append(_check("time_gap", "Time between the training and test periods", "not_run", None, "No dates given."))
    vario = None
    if targets:
        pts = [(x["center"], targets.get(x["id"])) for x in s if x["id"] in targets]
        vario = semivariogram([p[0] for p in pts], [p[1] for p in pts])
        checks.append(_check("spatial_dependence", "Spatial dependence of the target", "pass" if vario["bins"] else "not_run",
                             vario.get("median_nearest_neighbour_km"),
                             vario["note"] if not vario["bins"] else
                             f"Median nearest neighbour {vario['median_nearest_neighbour_km']} km; {vario['pairs_under_150_km']} pair(s) under 150 km. Indicative only."))
    else:
        checks.append(_check("spatial_dependence", "Spatial dependence of the target", "not_run", None, "No per-site target values given."))
    if duplicates is not None:
        n = len(duplicates["found"])
        crossing_dups = [p for p in duplicates["found"] if role_of.get(p["a"]) != role_of.get(p["b"])]
        checks.append(_check("near_duplicates", "Near-duplicate chips", "pass" if not crossing_dups else "fail", len(crossing_dups),
                             f"{n} near-duplicate pair(s) among {duplicates['n_images']} chips; {len(crossing_dups)} cross roles."))
    else:
        checks.append(_check("near_duplicates", "Near-duplicate chips", "not_run", None, "Not run."))
    if shift is not None and shift.get("median_psi") is not None:
        lvl = psi_level(shift["median_psi"])
        checks.append(_check("domain_shift", "Shift between the two roles", "pass" if lvl != "large" else "warn", shift["median_psi"],
                             f"Median PSI {shift['median_psi']} ({lvl}); {shift['n_large']} feature(s) with a large shift. Most different: "
                             f"{', '.join(shift['most_different']) or 'none'}."))
    else:
        checks.append(_check("domain_shift", "Shift between the two roles", "not_run", None, "Not run."))
    failed = [x for x in checks if x["status"] == "fail"]
    warned = [x for x in checks if x["status"] == "warn"]
    skipped = [x["id"] for x in checks if x["status"] == "not_run"]
    verdict = "fail" if failed else "conditional" if (warned or skipped) else "pass"
    return {"schema": "site-curator-certificate/1", "tool_version": tool_version,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"), "roster_sha256": roster_hash(s),
            "n_sites": len(s), "roles": {r: sum(1 for x in s if x.get("role") == r) for r in sorted({x.get("role") for x in s})},
            "role_sides": {r: fold(r) for r in sorted({x.get("role") for x in s})},
            "settings": c, "verdict": verdict, "checks": checks, "not_run": skipped,
            "min_distance_between_roles_km": md,
            "overlap": {lv: v for lv, v in group_summary(s, c)["levels"].items()},
            "overlap_groups": {"level": "ring", "n_groups": groups["n_groups"], "mixed_role_groups": [g for g in groups["groups"] if g["mixed_roles"]]},
            "spatial_dependence": vario, "near_duplicates": duplicates, "domain_shift": shift,
            "note": "A pass means the checks that were run found nothing. Checks marked not_run say nothing either way."}
