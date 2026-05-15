"""
app.py — Gradio interface for the figure & table miner.

Run locally:
    python app.py

Deploy to Hugging Face Spaces:
    1. Create a new Space (SDK: Gradio).
    2. Push these files: app.py, miner.py, linker.py, summarizer.py, requirements.txt
    3. Add ANTHROPIC_API_KEY as a Secret in the Space settings (or let users paste their own key into the UI).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Compatibility patch: Gradio 5 + huggingface_hub on HF Spaces sometimes
# trips a schema-walker bug where bool schemas (valid JSON Schema for "any")
# are passed where dicts are expected, breaking the /api/info endpoint and
# making the frontend show "No API found" on every click. Patch the private
# recursive function to skip bool inputs.
# Must run BEFORE `import gradio`.
# ---------------------------------------------------------------------------
import gradio_client.utils as _gcu
_orig_json_schema_to_python_type = _gcu._json_schema_to_python_type
def _safe_json_schema_to_python_type(schema, defs=None):
    if isinstance(schema, bool):
        return "Any"
    try:
        return _orig_json_schema_to_python_type(schema, defs)
    except Exception:
        return "Any"
_gcu._json_schema_to_python_type = _safe_json_schema_to_python_type
# ---------------------------------------------------------------------------

import json
import os
import tempfile

import gradio as gr

from miner import mine_pdf
from linker import link_context
from summarizer import summarize_all


def _figure_to_json(fig) -> dict:
    return {
        "index": fig.index,
        "number": fig.number,
        "page": fig.page,
        "caption": fig.caption,
        "context": fig.context,
        "summary": fig.summary,
    }


def _table_to_json(tab) -> dict:
    return {
        "index": tab.index,
        "number": tab.number,
        "page": tab.page,
        "caption": tab.caption,
        "context": tab.context,
        "markdown": tab.markdown,
        "summary": tab.summary,
    }


def process(pdf_file, api_key, do_summarize, model_choice):
    if pdf_file is None:
        yield "Upload a PDF first.", [], "", "", None
        return

    try:
        yield "Step 1/3 — Parsing PDF (this is the slow part on first run; docling downloads models)...", [], "", "", None

        pdf_path = pdf_file.name if hasattr(pdf_file, "name") else pdf_file
        extracted = mine_pdf(pdf_path)
        figures = extracted["figures"]
        tables = extracted["tables"]

        yield f"Step 2/3 — Linking discussion text ({len(figures)} figures, {len(tables)} tables found)...", [], "", "", None

        link_context(extracted["text"], figures, tables)

        if do_summarize:
            if not (api_key or os.environ.get("ANTHROPIC_API_KEY")):
                yield "ERROR: Summarization is on but no API key was provided. Paste a key or uncheck the box.", [], "", "", None
                return
            yield f"Step 3/3 — Summarizing {len(figures) + len(tables)} items with {model_choice}...", [], "", "", None
            summarize_all(figures, tables, api_key=api_key or None, model=model_choice)

        # Build the figure gallery
        gallery = []
        for fig in figures:
            label_bits = []
            if fig.number is not None:
                label_bits.append(f"Fig {fig.number}")
            else:
                label_bits.append(f"Fig (idx {fig.index})")
            if fig.page is not None:
                label_bits.append(f"p.{fig.page}")
            caption_snip = (fig.caption[:90] + "…") if len(fig.caption) > 90 else fig.caption
            label = " · ".join(label_bits) + ((" — " + caption_snip) if caption_snip else "")
            gallery.append((fig.image, label))

        # Build the table rendering (markdown of each table with its summary)
        table_md_chunks = []
        for tab in tables:
            chunk = []
            head = f"### Table {tab.number if tab.number is not None else tab.index}"
            if tab.page is not None:
                head += f" (page {tab.page})"
            chunk.append(head)
            if tab.caption:
                chunk.append(f"**Caption:** {tab.caption}")
            if tab.summary:
                chunk.append("**Summary:**")
                chunk.append("```json\n" + json.dumps(tab.summary, indent=2) + "\n```")
            chunk.append(tab.markdown or "_(could not render table)_")
            table_md_chunks.append("\n\n".join(chunk))
        tables_md = "\n\n---\n\n".join(table_md_chunks) if table_md_chunks else "_No tables detected._"

        # Build the full JSON output
        payload = {
            "figures": [_figure_to_json(f) for f in figures],
            "tables": [_table_to_json(t) for t in tables],
        }
        payload_str = json.dumps(payload, indent=2, default=str)

        # Write JSON to a temp file so the user can download it
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="mined_"
        )
        tmp.write(payload_str)
        tmp.close()

        status = f"Done. Extracted {len(figures)} figures and {len(tables)} tables."
        yield status, gallery, tables_md, payload_str, tmp.name

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        tail = "\n".join(tb.splitlines()[-15:])
        msg = (
            f"❌ Pipeline failed: {type(e).__name__}: {e}\n\n"
            f"--- Traceback (last frames) ---\n{tail}\n\n"
            f"If this is reproducible on a specific PDF, the PDF likely has an "
            f"unusual structure (scanned without OCR, encrypted, corrupt fonts, "
            f"or extremely large). Try opening it in a PDF reader to check."
        )
        yield msg, [], "", "", None


with gr.Blocks(title="Scientific Figure & Table Miner") as demo:
    gr.Markdown(
        "# Scientific Figure & Table Miner\n"
        "Upload any scientific PDF. The tool extracts figures, tables, the "
        "discussion text that references each one, and (optionally) a "
        "structured LLM-generated summary per item."
    )

    with gr.Row():
        with gr.Column(scale=1):
            pdf_input = gr.File(label="PDF", file_types=[".pdf"])
            do_summarize = gr.Checkbox(label="Use LLM to summarize each figure/table", value=True)
            api_key = gr.Textbox(
                label="Anthropic API key",
                placeholder="sk-ant-... (or set ANTHROPIC_API_KEY env var)",
                type="password",
            )
            model_choice = gr.Dropdown(
                label="Model",
                choices=["claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5-20251001"],
                value="claude-sonnet-4-6",
            )
            run_btn = gr.Button("Mine the paper", variant="primary")
            status = gr.Textbox(label="Status", interactive=False)

        with gr.Column(scale=2):
            with gr.Tabs():
                with gr.TabItem("Figures"):
                    gallery = gr.Gallery(
                        label="Extracted figures",
                        columns=2,
                        object_fit="contain",
                        allow_preview=True,
                        show_label=True,
                    )
                with gr.TabItem("Tables"):
                    tables_view = gr.Markdown()
                with gr.TabItem("Full JSON"):
                    json_view = gr.Code(language="json", label="Structured output")
                    json_download = gr.File(label="Download JSON", interactive=False)

    run_btn.click(
        process,
        inputs=[pdf_input, api_key, do_summarize, model_choice],
        outputs=[status, gallery, tables_view, json_view, json_download],
    )


if __name__ == "__main__":
    demo.launch()
