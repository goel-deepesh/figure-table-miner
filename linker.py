"""
linker.py — Attach the body-text discussion of each figure/table to its object.

The miner gives you captions. This module finds every paragraph that *mentions*
a figure or table by number (e.g. "...as shown in Fig. 3...") and attaches it.
That linked context is what makes a useful LLM summary possible.
"""

from __future__ import annotations

import re
from typing import Sequence

from miner import Figure, Table


# Matches: Fig 3, Fig. 3, Figure 3, Figures 3 and 4, Figs. 3-5
_FIG_REF_RE = re.compile(
    r"\b(?:fig(?:ure)?s?\.?)\s*(\d+(?:\s*[-–,and ]+\s*\d+)*)",
    re.IGNORECASE,
)
_TAB_REF_RE = re.compile(
    r"\b(?:tab(?:le)?s?\.?)\s*(\d+(?:\s*[-–,and ]+\s*\d+)*)",
    re.IGNORECASE,
)
# A caption block starts with "Figure 3." / "Table 2:" — skip these when linking
_CAPTION_START_RE = re.compile(
    r"^\s*(?:figure|fig\.?|table|tab\.?)\s*\d+\s*[.:]",
    re.IGNORECASE,
)


def _expand_numbers(raw: str) -> set[int]:
    """'3 and 5' -> {3,5} ; '3-5' -> {3,4,5} ; '3, 4' -> {3,4}"""
    nums: set[int] = set()
    # split on anything that isn't a digit or a range marker
    parts = re.split(r"[,\s]+and\s+|[,\s]+", raw.strip())
    for part in parts:
        if not part:
            continue
        if "-" in part or "–" in part:
            a, b = re.split(r"[-–]", part, maxsplit=1)
            try:
                a, b = int(a), int(b)
                if a <= b and b - a < 50:
                    nums.update(range(a, b + 1))
            except ValueError:
                pass
        else:
            try:
                nums.add(int(part))
            except ValueError:
                pass
    return nums


def _split_paragraphs(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text)]
    return [p for p in paras if p]


def link_context(
    text: str,
    figures: Sequence[Figure],
    tables: Sequence[Table],
    max_paragraphs_per_item: int = 5,
) -> None:
    """
    Mutates `figures` and `tables` in place — populates their `.context` lists.

    A figure/table is matched by its `.number` (parsed from caption). If a figure
    has no number, falls back to its 1-based `.index`.
    """
    paragraphs = _split_paragraphs(text)

    fig_buckets: dict[int, list[str]] = {}
    tab_buckets: dict[int, list[str]] = {}

    for para in paragraphs:
        if _CAPTION_START_RE.match(para):
            continue  # don't treat the caption itself as discussion text

        for m in _FIG_REF_RE.finditer(para):
            for n in _expand_numbers(m.group(1)):
                fig_buckets.setdefault(n, []).append(para)

        for m in _TAB_REF_RE.finditer(para):
            for n in _expand_numbers(m.group(1)):
                tab_buckets.setdefault(n, []).append(para)

    def _dedupe(seq: list[str]) -> list[str]:
        seen, out = set(), []
        for s in seq:
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out

    for fig in figures:
        key = fig.number if fig.number is not None else fig.index
        fig.context = _dedupe(fig_buckets.get(key, []))[:max_paragraphs_per_item]

    for tab in tables:
        key = tab.number if tab.number is not None else tab.index
        tab.context = _dedupe(tab_buckets.get(key, []))[:max_paragraphs_per_item]
