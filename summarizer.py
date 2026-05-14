"""
summarizer.py — Produce a structured JSON summary per figure / table using a
vision-capable LLM. Default: Anthropic Claude Sonnet. Swap providers freely;
all you need is a function that takes (image|markdown, caption, context) and
returns JSON.

The prompts ask for a tight schema so the output is searchable / embeddable
downstream (e.g. for the LENR dashboard's retrieval and topic modeling).
"""

from __future__ import annotations

import base64
import json
import os
import re
from io import BytesIO
from typing import Optional

import anthropic

from miner import Figure, Table


DEFAULT_MODEL = "claude-sonnet-4-6"


# ---------- prompts ----------

FIGURE_PROMPT = """You are extracting structured information from a figure in a scientific paper.

CAPTION:
{caption}

DISCUSSION TEXT FROM THE PAPER (paragraphs that reference this figure):
{context}

Examine the figure and return ONLY a JSON object with exactly these keys:

{{
  "figure_type": one of ["plot", "schematic", "apparatus_photo", "micrograph", "diagram", "equation", "map", "other"],
  "subject": one-sentence description of what the figure shows,
  "scientific_insight": 2-3 sentence explanation of the key scientific point the figure makes, drawing from BOTH the figure itself and the discussion text,
  "axes_or_elements": {{
      // For plots: keys are "x" and "y" (and "z" if 3D), values are "<label> (<units>)".
      // For non-plots: keys are short element names, values are short descriptions.
  }},
  "key_data_points": [
      // For plots/data figures: short strings naming numerical findings visible
      // (e.g. "excess power ~0.6 W at ~30 W input"). Empty list if not applicable.
  ],
  "embedded_equations": [
      // Strings of any equations visible inside the figure. Empty list if none.
  ]
}}

Do not wrap the JSON in markdown fences. Do not include any other text."""


TABLE_PROMPT = """You are extracting structured information from a table in a scientific paper.

CAPTION:
{caption}

TABLE CONTENT (markdown):
{table_md}

DISCUSSION TEXT FROM THE PAPER (paragraphs that reference this table):
{context}

Return ONLY a JSON object with exactly these keys:

{{
  "subject": one-sentence description of what the table reports,
  "scientific_insight": 2-3 sentence summary of the key takeaway from the table, drawing from BOTH the table values and the discussion text,
  "columns": [
      // List of column headers in the table.
  ],
  "row_count": integer number of data rows (excluding the header),
  "units": {{
      // Map of column name -> unit string, where applicable. Empty object if no units.
  }},
  "notable_values": [
      // 2-5 short strings naming the most important values or comparisons in the table.
  ]
}}

Do not wrap the JSON in markdown fences. Do not include any other text."""


# ---------- helpers ----------

def _pil_to_b64(image, fmt: str = "PNG") -> str:
    buf = BytesIO()
    image.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _format_context(context: list[str], char_limit: int = 4000) -> str:
    if not context:
        return "(No discussion text found for this item in the paper body.)"
    joined = "\n\n".join(context)
    if len(joined) > char_limit:
        joined = joined[:char_limit] + "\n... [truncated]"
    return joined


def _parse_json(text: str) -> dict:
    """Robust JSON parse — strips fences if the model added them anyway."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        return {"_parse_error": str(e), "_raw": text}


# ---------- public API ----------

class Summarizer:
    """Holds the API client so we don't reinstantiate per call."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model

    def summarize_figure(self, fig: Figure) -> dict:
        prompt = FIGURE_PROMPT.format(
            caption=fig.caption or "(no caption detected)",
            context=_format_context(fig.context),
        )
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": _pil_to_b64(fig.image),
                    }},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return _parse_json(msg.content[0].text)

    def summarize_table(self, tab: Table) -> dict:
        prompt = TABLE_PROMPT.format(
            caption=tab.caption or "(no caption detected)",
            table_md=tab.markdown[:6000],
            context=_format_context(tab.context),
        )
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_json(msg.content[0].text)


def summarize_all(figures, tables, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
    """Mutates figures/tables in place: populates `.summary` on each."""
    s = Summarizer(api_key=api_key, model=model)
    for fig in figures:
        try:
            fig.summary = s.summarize_figure(fig)
        except Exception as e:
            fig.summary = {"_error": str(e)}
    for tab in tables:
        try:
            tab.summary = s.summarize_table(tab)
        except Exception as e:
            tab.summary = {"_error": str(e)}
