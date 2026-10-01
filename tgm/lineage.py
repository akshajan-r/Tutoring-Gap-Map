"""Follow a school across URN changes so year-on-year trends don't break.

When a school converts to an academy (or is re-brokered to a new trust) it gets
a brand-new URN. GIAS records most of these as predecessor/successor links;
where it doesn't, a closure and an opening at the same postcode with a similar
name on (almost) the same day is almost certainly the same school.
"""
from __future__ import annotations

import re

import pandas as pd

_STOPWORDS = {"the", "school", "academy", "college", "of", "and", "a", "st", "saint"}


def _tokens(name: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    return {w for w in words if w not in _STOPWORDS}


def name_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


class _UnionFind:
    def __init__(self):
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[min(ra, rb)] = max(ra, rb)


def one_to_one_links(links: pd.DataFrame) -> pd.DataFrame:
    """(predecessor, successor) pairs where neither side was merged or split.

    Amalgamations and splits would put two schools' results in the same
    lineage-year, so they're left as separate lineages.
    """
    lt = links["link_type"].str.lower()
    plain = ~lt.str.contains("amalgamat|merge|split", regex=True)
    succ = links[plain & lt.str.startswith("successor")][["urn", "link_urn"]]
    pred = links[plain & lt.str.startswith("predecessor")][["link_urn", "urn"]]
    pairs = pd.concat([
        succ.set_axis(["pred", "succ"], axis=1),
        pred.set_axis(["pred", "succ"], axis=1),
    ]).drop_duplicates()
    pairs = pairs[pairs["pred"] != pairs["succ"]]
    n_succ = pairs.groupby("pred")["succ"].transform("nunique")
    n_pred = pairs.groupby("succ")["pred"].transform("nunique")
    return pairs[(n_succ == 1) & (n_pred == 1)].reset_index(drop=True)


def postcode_matches(gias: pd.DataFrame, urns: set[int], max_gap_days: int = 60,
                     min_similarity: float = 0.5) -> pd.DataFrame:
    """Closed -> opened pairs at the same postcode with similar names."""
    g = gias[gias["urn"].isin(urns) & gias["postcode"].notna()]
    closed = g[g["close_date"].notna()][["urn", "postcode", "school_name", "close_date"]]
    opened = g[g["open_date"].notna()][["urn", "postcode", "school_name", "open_date"]]
    cand = closed.merge(opened, on="postcode", suffixes=("_old", "_new"))
    cand = cand[cand["urn_old"] != cand["urn_new"]]
    gap = (cand["open_date"] - cand["close_date"]).dt.days.abs()
    cand = cand[gap <= max_gap_days]
    sim = [name_similarity(a, b) for a, b in zip(cand["school_name_old"], cand["school_name_new"])]
    cand = cand[pd.Series(sim, index=cand.index, dtype=float) >= min_similarity]
    return cand.rename(columns={"urn_old": "pred", "urn_new": "succ"})[["pred", "succ"]]


def build_lineage(gias: pd.DataFrame, links: pd.DataFrame | None,
                  results: pd.DataFrame) -> pd.DataFrame:
    """Return urn -> lineage_id for every URN with results.

    lineage_id is the newest URN in the chain that has results, so it names the
    school as it was most recently assessed.

    Also returns how each URN was linked: 'self', 'gias_link' or 'postcode_match'.
    """
    urns = set(results["urn"].unique())
    uf = _UnionFind()
    method: dict[int, str] = {u: "self" for u in urns}

    if links is not None and len(links):
        pairs = one_to_one_links(links)
        # Walk chains through URNs that never sat GCSEs (e.g. a short-lived interim URN).
        for p, s in pairs.itertuples(index=False):
            uf.union(int(p), int(s))
            for u in (p, s):
                if u in method:
                    method[u] = "gias_link"

    groups: dict[int, list[int]] = {}
    for u in urns:
        groups.setdefault(uf.find(u), []).append(u)
    unlinked = {members[0] for members in groups.values() if len(members) == 1}
    for p, s in postcode_matches(gias, unlinked).itertuples(index=False):
        if uf.find(p) != uf.find(s):
            uf.union(int(p), int(s))
            method[p] = method[s] = "postcode_match"

    out = pd.DataFrame({"urn": sorted(urns)})
    out["root"] = out["urn"].map(uf.find)
    out["lineage_method"] = out["urn"].map(method)

    # Guard: a lineage must never have two URNs with results in the same year.
    years = results[["urn", "year_start"]].merge(out, on="urn")
    clash = years.groupby(["root", "year_start"])["urn"].nunique()
    bad_roots = set(clash[clash > 1].index.get_level_values("root"))
    bad = out["root"].isin(bad_roots)
    out.loc[bad, "root"] = out.loc[bad, "urn"]
    out.loc[bad, "lineage_method"] = "self"

    out["lineage_id"] = out.groupby("root")["urn"].transform("max")
    out.loc[out.groupby("lineage_id")["urn"].transform("size") == 1, "lineage_method"] = "self"
    return out[["urn", "lineage_id", "lineage_method"]]
