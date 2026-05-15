"""
miner.py — Extract figures, tables, and reading-order text from any scientific PDF.

Uses IBM's `docling` for layout-aware parsing. Handles vector figures, multi-column
papers, table structure, and reading order — none of which raw PyMuPDF gives you
cleanly.

Public entry point: mine_pdf(pdf_path) -> dict
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import PictureItem, TableItem


# ---------- data containers ----------

@dataclass
class Figure:
    index: int                  # 1-based position in document
    number: Optional[int]       # parsed from caption, e.g. "Figure 3" -> 3
    page: Optional[int]
    image: object               # PIL.Image.Image
    caption: str
    context: list[str] = field(default_factory=list)  # filled by linker.py
    summary: Optional[dict] = None                     # filled by summarizer.py


@dataclass
class Table:
    index: int
    number: Optional[int]
    page: Optional[int]
    markdown: str
    dataframe: object           # pandas.DataFrame
    caption: str
    context: list[str] = field(default_factory=list)
    summary: Optional[dict] = None


# ---------- helpers ----------

_FIG_NUM_RE = re.compile(r"^\s*(?:figure|fig\.?)\s*(\d+)", re.IGNORECASE)
_TAB_NUM_RE = re.compile(r"^\s*(?:table|tab\.?)\s*(\d+)", re.IGNORECASE)


def _parse_number(caption: str, pattern: re.Pattern) -> Optional[int]:
    if not caption:
        return None
    m = pattern.match(caption)
    return int(m.group(1)) if m else None


def _page_of(item) -> Optional[int]:
    """Best-effort page number from a docling item's provenance."""
    try:
        return item.prov[0].page_no
    except Exception:
        return None


# ---------- main entry point ----------

def mine_pdf(pdf_path: str, images_scale: float = 2.0) -> dict:
    """
    Parse a scientific PDF and return its figures, tables, and full text.

    Args:
        pdf_path: filesystem path to the PDF
        images_scale: rendering scale for figure images (2.0 = 144 DPI-ish)

    Returns:
        {
          "figures": list[Figure],
          "tables":  list[Table],
          "text":    str   (markdown with reading order),
        }
    """
    pipe_opts = PdfPipelineOptions()
    pipe_opts.images_scale = images_scale
    pipe_opts.generate_picture_images = True

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipe_opts)}
    )

    result = converter.convert(pdf_path)
    doc = result.document

    figures: list[Figure] = []
    tables: list[Table] = []

    for element, _level in doc.iterate_items():
        if isinstance(element, PictureItem):
            try:
                img = element.get_image(doc)
            except Exception:
                img = None
            if img is None:
                continue
            caption = (element.caption_text(doc) or "").strip()
            figures.append(Figure(
                index=len(figures) + 1,
                number=_parse_number(caption, _FIG_NUM_RE),
                page=_page_of(element),
                image=img,
                caption=caption,
            ))

        elif isinstance(element, TableItem):
            try:
                md = element.export_to_markdown(doc)
            except Exception:
                md = ""
            try:
                df = element.export_to_dataframe(doc)
            except Exception:
                df = None
            caption = (element.caption_text(doc) or "").strip()
            tables.append(Table(
                index=len(tables) + 1,
                number=_parse_number(caption, _TAB_NUM_RE),
                page=_page_of(element),
                markdown=md,
                dataframe=df,
                caption=caption,
            ))

    return {
        "figures": figures,
        "tables": tables,
        "text": doc.export_to_markdown(),
        "doc": doc,
    }
