# Changes in this revision

## Bugs fixed
- **Tabs stopped responding (blank page after the first view).** `streamlit_app.py` used `import app`. A module body runs once per server process, so after the first page render every rerun (tab click, widget change) drew nothing, for every user. It now runs `app.py` with `runpy` on each rerun. Regression test: `tests/test_entrypoint.py`.
- Removed the deprecated `st.components.v1.iframe` script injection (it logged a warning on every rerun and added an iframe for cosmetic effects only).
- Raw `None`/unformatted numbers in the Financial Analysis tables; midnight timestamps shown in periods; lower-case table headers; status icon text clashing with the font override.
- The two-button upload flow no longer covers the top of every page; Analyze / Re-analyze live in the sidebar.

## Interface
- Enterprise (SAP Fiori / Horizon inspired) theme: `static/css/style.css`, palette in `src/msme_ews/theme.py`, Streamlit theme in `.streamlit/config.toml`.
- New Overview: portfolio KPI cards, risk band chart, warning frequency chart, ranked worklist (`tabs/home.py`, helpers in `src/msme_ews/screening.py`).
- Marketing hero banners, emoji and decorative copy removed from the working tabs.

## Not changed
- Scoring rules and the analysis engine (`src/msme_ews`) are unchanged; all original tests still pass (129 total including the new ones).
- `web/` (the static Netlify mirror) was not modified and was not fully testable here because it loads Plotly and SheetJS from a CDN.

## Follow-up fix
- `POST /predict` returned a 500 (`AttributeError: 'NoneType' ... 'get'`) when no trained model file existed, because `load_model_bundle` returns `None` rather than raising. `api.py` now returns the intended 503 "Train a model before using the API." Regression test added in `tests/test_api.py`.
