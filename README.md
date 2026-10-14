# Credit Risk Analytics

An upload-driven credit risk workspace for MSME financial statements, styled as an enterprise application (navy shell bar, side navigation, KPI cards, worklists). Upload a CSV, Excel or text-based PDF statement and the app scores every company and period, raises early warnings, and exports reports. Nothing is shown until you upload data.

## Run it

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Try it with `sample_data/sample_msme_financials.csv` (synthetic, 30 companies x 3 periods), or use the download button on the Overview page.

## Workspace

| View | Purpose |
|---|---|
| Overview | Portfolio cockpit: KPI cards, risk band mix, most frequent warnings, ranked risk worklist |
| Financial Analysis | Statement values, ratios and trends for the selected company and period |
| Risk Assessment | 0-100 risk index, category, drivers and protective factors |
| Early Warnings | Seven deterioration rules with observed value and threshold |
| Data Intelligence | Schema, quality, anomalies and charts for the upload |
| AI Assistant | Credit and dataset Q&A (rule-based, optional LLM) |
| Reports | PDF and Excel exports |
| Methodology / About | Definitions and limits; project background |

Pick the company and period in the sidebar; upload, analysis and selection all live there.

## Tests

```bash
python -m pytest tests -q
```

`tests/test_entrypoint.py` guards the deployed entrypoint (`streamlit_app.py`), which must execute `app.py` on every rerun.

## Financial statement uploads

The Streamlit application accepts CSV, XLSX, XLS, and text-based PDF statements. Upload processing runs locally: it reads workbook sheets and PDF tables/text, detects common financial fields, parses Indian-number formats and units, calculates available measures, and reports observed data coverage. Scanned-image PDFs are not OCR processed.

Dataset-specific supervised models are evaluated only when an uploaded dataset contains an evaluable target; these are hold-out metrics, not row-level predictions or calibrated probabilities of default. Where no target is available, the app reports transparent rule-based indices, statistical patterns, and anomaly signals. Rule-based indices are heuristic points, not probabilities of default or lending decisions. PDF and Excel reports are generated from the active upload's analysis.

## Free LLM copilot (optional)

The AI Copilot and Dataset Copilot answer from the active upload using a transparent rule-based engine by default; no network call is made. To generate answers with a free language model instead, configure any OpenAI-compatible chat endpoint through Streamlit secrets (`.streamlit/secrets.toml`) or environment variables:

```toml
LLM_API_BASE = "http://localhost:11434/v1"   # local Ollama server: free, no key, data stays on the machine
LLM_MODEL = "llama3.2"
```

Free cloud options include Groq's free tier (`LLM_API_BASE = "https://api.groq.com/openai/v1"` plus `LLM_API_KEY`) and OpenRouter's `:free` models (`https://openrouter.ai/api/v1`). Only the derived credit context for the selected record, or compact dataset metadata, is sent to the endpoint — never the uploaded file. If the endpoint is unreachable, times out, or returns an empty answer, the copilot automatically falls back to the rule-based engine, and every answer is labeled with its source.

## Synthetic development data

`python -m msme_ews.demo data/demo_msme.csv --companies 240 --periods 3` (with `src` on `PYTHONPATH`) writes a deterministic synthetic company-period CSV for development and tests. The application never loads it; uploads are the only data source for analysis, and models trained on this generator are flagged and refused by the prediction API.
