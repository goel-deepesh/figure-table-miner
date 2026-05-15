---
title: Figure & Table Miner
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 5.29.0
app_file: app.py
pinned: false
license: mit
python_version: "3.12"
---

# Scientific Figure & Table Miner

Takes any scientific PDF, gives you back its figures, tables, the body-text
discussion of each, and a structured LLM-generated summary per item. Designed
for integration into the LENR Dashboard (or any retrieval / topic-modeling
pipeline that wants to embed figure- and table-level content).

## What's in here

```
miner.py        # docling-based extraction: figures + tables + reading-order text
linker.py       # finds the paragraphs that reference each figure / table
summarizer.py   # vision-LLM structured summarization (Claude by default)
app.py          # Gradio UI — the deployable surface
requirements.txt
```

## Pipeline

```
PDF
 │
 ├── miner.mine_pdf()         ──►  figures, tables, full markdown text
 │
 ├── linker.link_context()    ──►  attaches body paragraphs to each fig/table by number
 │
 └── summarizer.summarize_all() ──►  JSON summary per item:
                                       { figure_type, subject, scientific_insight,
                                         axes_or_elements, key_data_points,
                                         embedded_equations }
```

## Run locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python app.py
```

First run downloads docling's layout models (~1-2 GB, one-time). After that a
~10-page paper parses in 30-60 seconds on CPU.

## Use it as a library (no UI)

```python
from miner import mine_pdf
from linker import link_context
from summarizer import summarize_all

ex = mine_pdf("paper.pdf")
link_context(ex["text"], ex["figures"], ex["tables"])
summarize_all(ex["figures"], ex["tables"])

for fig in ex["figures"]:
    print(fig.number, fig.caption, fig.summary)
```

## Deploy to Hugging Face Spaces

1. `huggingface-cli login`
2. Create a Space → SDK: **Gradio** → Hardware: CPU Basic is fine; GPU is faster on first parse
3. `git clone` your new Space repo, copy these files into it, push
4. In the Space's **Settings → Repository secrets**, add `ANTHROPIC_API_KEY`
5. Wait for build (~5 min). You now have a public URL like
   `https://huggingface.co/spaces/<you>/figure-miner`

## Integrate into lenrdashboard.com

Two reasonable patterns:

**A. Iframe embed.** Add `<iframe src="https://huggingface.co/spaces/<you>/figure-miner" width="100%" height="900"></iframe>` to a page on the dashboard. Zero backend work; users get the full UI inline.

**B. Programmatic call.** Use Gradio's client to call the Space from your dashboard backend:

```python
from gradio_client import Client
client = Client("<you>/figure-miner")
result = client.predict("paper.pdf", "", True, "claude-sonnet-4-6", api_name="/process")
```

Pattern B lets the dashboard own the UX and just use the miner as a service. The
JSON output is what you'd index into your retrieval / topic-modeling backend.

## Why docling, not raw PyMuPDF

Many scientific figures are vector PDFs (drawing operations), not embedded
raster images, so `page.get_images()` skips them entirely. docling renders
figure regions from layout-model bounding boxes, so it gets both raster and
vector figures, plus reading order across multi-column papers — which makes
the text→figure linker work properly on arbitrary papers.

## Knobs

- `images_scale` in `miner.mine_pdf()` — increase for higher-res figure images
  (default 2.0 ≈ 144 DPI)
- `max_paragraphs_per_item` in `linker.link_context()` — cap on how much
  discussion text is attached per figure (default 5)
- `model` in `summarizer.Summarizer` — swap to opus for harder figures or
  haiku for speed/cost
- `FIGURE_PROMPT` / `TABLE_PROMPT` in `summarizer.py` — change the JSON schema
  if you want different fields surfaced for the dashboard

## Known limits

- Scanned (image-only) PDFs need OCR; docling can do it but you need to enable
  OCR in `PdfPipelineOptions` (`do_ocr=True`) and accept slower parsing.
- Figures with multi-panel labels (a/b/c) are extracted as a single image —
  panel-level summarization is on the roadmap.
- Equation OCR inside figures is handled by the vision LLM, not extracted as
  LaTeX. If you need parseable LaTeX, plug `pix2tex` / `nougat` into the
  summarizer step.
