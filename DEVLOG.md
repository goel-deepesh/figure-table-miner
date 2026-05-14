# DEVLOG

Append-only log of design decisions, what changed, what didn't work, and why.
Newest entries at the bottom. Don't rewrite history here — commit fixes go in git.

---

## 2026-05-14 — v0.1 — initial scaffold

**Goal:** Stand up an end-to-end pipeline that takes any scientific PDF and
produces structured per-figure / per-table output, deployable as a Gradio app.

**Decisions:**
- Switched the extraction backend from raw PyMuPDF (notebook v0) to **docling**.
  Reason: PyMuPDF's `doc.extract_image()` only yields raster images, which
  silently skips vector figures (most plots in modern scientific PDFs). docling
  uses a layout model + region rendering, so it gets both.
- Caption-to-figure pairing now comes from docling's layout (not center-distance
  matching). More robust on multi-column papers.
- Added a `linker.py` step that scans body text for "Fig N" / "Table N"
  references and attaches surrounding paragraphs to each figure/table. This is
  the "figure context" the project brief calls out — wasn't in the notebook v0.
- Summarization uses Claude Sonnet 4.6 by default with vision input. Schema is
  structured JSON so it's downstream-indexable for the LENR dashboard.

**Stack:**
- `miner.py` (docling) → `linker.py` (regex on body text) → `summarizer.py`
  (Anthropic vision API) → `app.py` (Gradio).

**Open questions:**
- Quality on LENR-conference-proceedings PDFs (older scans) — might need OCR
  enabled. Test before deploy.
- Whether multi-panel figures (a/b/c) need panel-level splitting.

---

## 2026-05-14 — v0.1.1 — Gradio type-mismatch fix

**Bug:** First click on "Mine the paper" crashed with
`AttributeError: 'list' object has no attribute 'expandtabs'` from inside
`gradio/components/markdown.py`.

**Cause:** Progress `yield` statements were passing `[]` to the `tables_view`
slot, but that's a `gr.Markdown` component which needs `str`. Same for
`json_download` which needs `None` not `""`.

**Fix:** Corrected types in all intermediate yields and the no-PDF early return.

---

## 2026-05-14 — v0.1.2 — transformers version pin

**Bug:** `ValueError: ... model type `rt_detr_v2` but Transformers does not
recognize this architecture`.

**Cause:** docling's layout model uses RT-DETR v2, which needs
`transformers >= 4.49`. Local env had an older version.

**Fix:** Pinned `transformers>=4.49`, `docling>=2.40`,
`docling-ibm-models>=3.4` in `requirements.txt`. Reinstalled.

---

## (next entry goes here)

<!--
Template for new entries:

## YYYY-MM-DD — vX.Y — short title

**Goal / Bug:**

**What I tried:**

**What worked / didn't:**

**Decision:**
-->
