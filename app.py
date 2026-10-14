"""Modular Streamlit router for the Credit Risk AI workspace.

This file is now a lightweight router: startup, navigation, backend init,
session state, service calls and per-tab dispatch. The heavy lifting lives
in:

* ``pages/``          static HTML shells, one per tab (+ layout.html)
* ``tabs/``           per-tab Python renderers (``render(ctx)``)
* ``services/``       backend logic: data, credit and AI services
* ``static/css``      the canonical stylesheet (injected once, below)
* ``static/js``       per-tab browser enhancements

Static-site mirror
------------------
A standalone, dependency-free JavaScript mirror of this workspace lives in
``web/`` (one functional HTML file per tab + ``web/assets/js/`` engine).
It is deployed to Netlify via ``netlify.toml`` (publish = ``web/``).
This Streamlit app remains the Python deployment target
(Streamlit Community Cloud via ``streamlit_app.py``).
"""


from __future__ import annotations

import sys
from pathlib import Path

# Robust path resolution for Streamlit Cloud and local development
def _resolve_src_dir() -> Path:
    """Resolve the src directory path robustly across environments."""
    candidates = [
        Path(__file__).resolve().parent / "src",  # Standard: app.py in root, src/ sibling
        Path.cwd() / "src",                         # Streamlit Cloud: cwd is repo root
        Path(__file__).resolve().parent.parent / "src",  # Nested deployment
    ]
    for candidate in candidates:
        if (candidate / "msme_ews" / "__init__.py").exists():
            return candidate
    # Last resort: look for the package anywhere under the repo (e.g. a nested upload folder).
    root = Path(__file__).resolve().parent
    for init in root.rglob("msme_ews/__init__.py"):
        return init.parent.parent
    return candidates[0]

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

SRC_DIR = _resolve_src_dir()
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if not (SRC_DIR / "msme_ews" / "__init__.py").exists():
    import streamlit as _st

    _st.error(
        "The analysis package is missing from this deployment: `src/msme_ews/` was not found. "
        "Upload the whole `src` folder to the GitHub repository (next to `app.py`), then reboot the app."
    )
    _st.stop()

import pandas as pd
import streamlit as st

from msme_ews.theme import STYLESHEET
from services import ai_service
from services.data_service import (
    _content_signature,
    _cached_dataset_profile,
    _cached_document_extraction,
    _cached_financial_features,
    _cached_financial_frame,
    _register_dataset,
)
from services.credit_service import (
    _cached_financial_analysis,
    get_bundle,
    portfolio_analysis_for,
    recommendations_for_selection,
    selected_assessment,
)
from tabs import (
    about,
    ai_assistant,
    data_intelligence as data_intelligence_page,
    early_warning,
    financial_health,
    home,
    methodology,
    reports,
    risk_prediction,
)
from tabs.common import period_label
from tabs.context import TabContext

st.set_page_config(
    page_title="Credit Risk Analytics",
    page_icon=":material/shield:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Optional free LLM for the embedded AI Credit Copilot panels. Settings are
# loaded in services.ai_service from LLM_API_BASE / LLM_API_KEY / LLM_MODEL /
# LLM_TIMEOUT in Streamlit secrets or the environment. Leave unconfigured to
# keep the transparent rule-based engine.
LLM_SETTINGS = ai_service.LLM_SETTINGS

# Inject the canonical stylesheet from static/css/style.css.
st.markdown(STYLESHEET, unsafe_allow_html=True)

NAVIGATION = {
    "Overview": "Home",
    "Financial Analysis": "MSME Financial Health",
    "Risk Assessment": "Risk Prediction",
    "Early Warnings": "Early-Warning Indicators",
    "Data Intelligence": "Data Intelligence",
    "AI Assistant": "AI Assistant",
    "Reports": "Reports",
    "Methodology": "Methodology",
    "About": "About",
}


def _render_static_page(module, ctx: TabContext) -> None:
    """Dispatch About/Methodology, which work with or without an upload."""
    module.render(ctx)
    st.stop()


# ── Workspace: navigation, upload and selectors live in the sidebar so the
# main area belongs 100% to the ACTIVE tab. Nothing renders for another tab.
st.sidebar.markdown("<div class='nav-group'>Workspace</div>", unsafe_allow_html=True)
selected_navigation = st.sidebar.radio("Workspace", list(NAVIGATION), label_visibility="collapsed")
page = NAVIGATION[selected_navigation]
# Read-only mirror of the navigation radio. Never written back into a widget
# key, so tab switches can never fight Streamlit's widget state and freeze.
if st.session_state.get("current_page") != page:
    st.session_state["current_page"] = page

st.sidebar.markdown("### Data source")
uploaded = st.sidebar.file_uploader(
    "Upload financial statement",
    type=["csv", "xlsx", "xls", "pdf"],
    key="financial_csv_upload",
    help="CSV, Excel workbooks, and text-based PDFs are processed locally. Scanned PDF images require OCR and are not supported.",
)
st.sidebar.caption("CSV, XLSX, XLS or text PDF. Processed in this session only.")
document_result = None
data_intelligence = None
if uploaded is not None:
    try:
        upload_token = (uploaded.file_id, uploaded.name, uploaded.size)
        same_upload = st.session_state.get("_upload_token") == upload_token
        if same_upload:
            upload_signature = st.session_state["_upload_signature"]
            uploaded_content = b""
        else:
            upload_signature = _content_signature(uploaded)
            uploaded_content = uploaded.getvalue()
            st.session_state["_upload_token"] = upload_token
            st.session_state["_upload_signature"] = upload_signature
            st.session_state["_upload_analysis_revision"] = 0
            # New file invalidates every downstream result immediately so stale
            # metrics can never linger while navigating between pages.
            for _stale_key in (
                "_upload_pipeline", "_upload_pipeline_key",
                "_financial_selection_cache", "_portfolio_analysis_cache",
                "_intelligence_report_cache", "_credit_report_cache",
                "_company_reports_cache", "_reports_intelligence_cache",
                "copilot_history", "credit_copilot_response",
                "credit_copilot_source", "credit_copilot_signature",
                "company_filter", "period_filter",
            ):
                st.session_state.pop(_stale_key, None)
            # Canonical aliases required by the acceptance spec. They mirror the
            # authoritative pipeline state so external checks can introspect it.
            st.session_state.pop("uploaded_data", None)
            st.session_state.pop("financial_metrics", None)
            st.session_state.pop("risk_result", None)
            st.session_state.pop("warnings", None)
            # Reset company/period selectors for the new file. They are popped
            # BEFORE the widgets are instantiated below, so Streamlit never sees
            # a stale widget value from the previous file (the classic freeze).
            st.session_state.pop("company_filter", None)
            st.session_state.pop("period_filter", None)
        analysis_revision = int(st.session_state.get("_upload_analysis_revision", 0))
        upload_pipeline_key = (upload_signature, uploaded.name, analysis_revision)
        has_current_analysis = st.session_state.get("_upload_pipeline_key") == upload_pipeline_key
        analyze_clicked = st.sidebar.button(
            "Analyze Dataset",
            disabled=has_current_analysis,
            key="analyze_upload",
            type="primary",
            width="stretch",
        )
        reanalyze_clicked = st.sidebar.button(
            "Re-analyze",
            disabled=not has_current_analysis,
            key="re_analyze_upload",
            width="stretch",
        )
        if reanalyze_clicked:
            analysis_revision += 1
            st.session_state["_upload_analysis_revision"] = analysis_revision
        upload_pipeline_key = (upload_signature, uploaded.name, analysis_revision)
        if not has_current_analysis and not analyze_clicked and not reanalyze_clicked:
            if page == "About":
                _render_static_page(about, TabContext(page=page))
            elif page == "Methodology":
                _render_static_page(methodology, TabContext(page=page))
            else:
                st.success("File loaded")
                st.info("Select Analyze Dataset in the sidebar to process this file.")
            st.stop()
        if st.session_state.get("_upload_pipeline_key") != upload_pipeline_key:
            if not uploaded_content:
                uploaded_content = uploaded.getvalue()
            with st.status("Analyzing dataset...", expanded=True) as progress:
                try:
                    document_result = _cached_document_extraction(
                        uploaded_content,
                        uploaded.name,
                        analysis_revision,
                        upload_signature,
                    )
                    progress.update(label="Detecting variables...")
                    data_intelligence, financial_columns = _cached_dataset_profile(
                        document_result.frame,
                        uploaded.name,
                        analysis_revision,
                        upload_signature,
                    )
                    progress.update(label="Running risk analysis...")
                    financial_frame = (
                        _cached_financial_frame(
                            document_result.frame,
                            uploaded.name,
                            analysis_revision,
                            upload_signature,
                        )
                        if financial_columns else None
                    )
                    financial_base = (
                        _cached_financial_features(financial_frame)
                        if financial_frame is not None else None
                    )
                    progress.update(label="Analysis complete", state="complete", expanded=False)
                except Exception:
                    # Mark the status as failed so the spinner can never hang,
                    # then let the outer handler render one friendly banner.
                    # Streamlit control-flow stops inherit BaseException and
                    # pass through this handler untouched.
                    progress.update(label="Analysis failed", state="error", expanded=True)
                    raise
            st.session_state["_upload_pipeline_key"] = upload_pipeline_key
            st.session_state["_upload_pipeline"] = {
                "document": document_result,
                "intelligence": data_intelligence,
                "financial_columns": financial_columns,
                "financial_frame": financial_frame,
                "financial_base": financial_base,
            }
            # Canonical aliases: single source of truth, mirrored for the spec.
            st.session_state["uploaded_data"] = document_result.frame
            st.session_state["financial_metrics"] = data_intelligence.get("financial_metrics")
        else:
            cached_upload = st.session_state["_upload_pipeline"]
            document_result = cached_upload["document"]
            data_intelligence = cached_upload["intelligence"]
            financial_columns = cached_upload["financial_columns"]
            financial_frame = cached_upload["financial_frame"]
            financial_base = cached_upload["financial_base"]
            st.session_state["uploaded_data"] = document_result.frame
            st.session_state["financial_metrics"] = data_intelligence.get("financial_metrics")
        frame = financial_frame
        # NOTE: per-tab rendering happens AFTER the selector block below. Only
        # the Data Intelligence early-exit renders here so a non-financial
        # upload still shows its profile instead of a dead page.
        if page == "Data Intelligence" or not financial_columns:
            early_ctx = TabContext(
                document_result=document_result,
                data_intelligence=data_intelligence,
                financial_columns=financial_columns,
                upload_signature=upload_signature,
                analysis_revision=analysis_revision,
                uploaded=uploaded,
                page=page,
            )
            data_intelligence_page.render(early_ctx)
            st.stop()
    except Exception as error:
        # One friendly banner instead of a raw traceback that takes down every
        # tab. Streamlit's st.stop()/st.rerun control flow inherits
        # BaseException, so it always passes through this handler untouched.
        st.error(f"Dataset analysis failed: {error}")
        if page == "About":
            _render_static_page(about, TabContext(page=page))
        elif page == "Methodology":
            _render_static_page(methodology, TabContext(page=page))
        st.stop()
else:
    if page in {"About", "Methodology", "Home", "AI Assistant"}:
        if page == "About":
            _render_static_page(about, TabContext(page=page))
        elif page == "Methodology":
            _render_static_page(methodology, TabContext(page=page))
        elif page == "Home":
            home.render_empty()
            st.stop()
        else:  # AI Assistant without data: support mode only
            ai_assistant.render_empty()
            st.stop()
    else:
        st.info("Upload a dataset to generate analysis.")
        st.warning("No financial dataset uploaded.")
        st.caption(
            "Upload an Excel, CSV, or supported financial statement in the sidebar to begin. "
            "Every metric, risk score, chart, warning and report is computed from the uploaded "
            f"file. The {selected_navigation} page analyses the active upload; Overview, "
            "Methodology and About are available without data."
        )
    st.stop()

# ── Backend init: model bundle, dataset registry, selectors ─────────────
bundle = get_bundle()
features, flags = financial_base
dataset_key = repr(upload_pipeline_key)
_register_dataset(
    dataset_key,
    frame,
    features,
    flags,
    uploaded.name,
)

if "company_id" in frame:
    company_values = frame["company_id"].astype(str)
    company_options = company_values.drop_duplicates().tolist()
else:
    company_values = pd.Series(["All records"] * len(frame), index=frame.index)
    company_options = ["All records"]
# Guard against a stale company value carried over from a previous upload:
# if it is no longer in this file's options, reset BEFORE the widget is built.
if st.session_state.get("company_filter") not in company_options:
    st.session_state.pop("company_filter", None)

# Selectors live in the sidebar so the main area belongs
# 100% to the active tab. They are built once here; per-tab code below only
# READS selected_company / row_index and never renders another tab's blocks.
st.sidebar.markdown("### Selection")
selected_company = st.sidebar.selectbox("Company", company_options, key="company_filter")

if "company_id" in frame:
    company_rows = [
        position
        for position, company in enumerate(company_values)
        if company == selected_company
    ]
else:
    company_rows = list(range(len(frame)))

# Resolve the period row from the selected company. The widget below is the
# single owner of the "period_filter" value — never write to that key after
# the widget exists, or Streamlit raises StreamlitAPIException and the tab
# appears frozen. So compute the safe default here, pass it as index=, and
# read the widget's return value instead of poking session_state.
if company_rows:
    _stored_period = st.session_state.get("period_filter")
    _default_row = _stored_period if _stored_period in company_rows else company_rows[0]
    _default_index = company_rows.index(_default_row)
else:
    _default_index = 0

_period_position = st.sidebar.selectbox(
    "Period",
    options=company_rows,
    index=_default_index,
    format_func=lambda index: period_label(
        frame.iloc[index].get("period", f"Record {index + 1}")
    ),
    key="period_filter",
)
row_index = int(_period_position) if company_rows else 0
with st.sidebar:
    analyze_state = "Analysed" if st.session_state.get("_upload_pipeline_key") == upload_pipeline_key else "Ready"
    st.caption(f"{uploaded.name} · {len(document_result.frame):,} records · {analyze_state}")

# ── Selection cache: one company-period, resolved once ────────────────────
selection_cache_key = (upload_pipeline_key, int(row_index))
selection_cache = st.session_state.setdefault("_financial_selection_cache", {})
if selection_cache_key in selection_cache:
    cached_selection = selection_cache[selection_cache_key]
    selected = cached_selection["selected"]
    selected_features = cached_selection["selected_features"]
    financial_analysis = cached_selection["financial_analysis"]
    active_warning_signals = cached_selection["active_warning_signals"]
    recommendations = cached_selection["recommendations"]
    model_available_for_record = cached_selection["model_available"]
    current_assessment = cached_selection["assessment"]
else:
    selected, selected_features = frame.iloc[[row_index]], features.iloc[[row_index]]
    financial_analysis = _cached_financial_analysis(dataset_key, row_index)
    active_warning_signals = flags.iloc[row_index][flags.iloc[row_index]].index.tolist()
    recommendations = recommendations_for_selection(
        frame.iloc[row_index],
        financial_analysis,
        active_warning_signals,
    )
    model_available_for_record = False
    current_assessment = selected_assessment(frame, row_index, financial_analysis)
    selection_cache[selection_cache_key] = {
        "selected": selected,
        "selected_features": selected_features,
        "financial_analysis": financial_analysis,
        "active_warning_signals": active_warning_signals,
        "recommendations": recommendations,
        "model_available": model_available_for_record,
        "assessment": current_assessment,
    }
    if len(selection_cache) > 24:
        oldest_key = next(iter(selection_cache))
        selection_cache.pop(oldest_key, None)

portfolio_analysis = None
if (
    data_intelligence is not None
    and data_intelligence["dataset_type"] in {"Customer dataset", "Loan/credit dataset"}
):
    portfolio_analysis = portfolio_analysis_for(document_result.frame, upload_pipeline_key)

# ── Router: exactly one tab renders per run ───────────────────────────────
ctx = TabContext(
    frame=frame,
    features=features,
    flags=flags,
    row_index=row_index,
    selected=selected,
    selected_features=selected_features,
    financial_analysis=financial_analysis,
    active_warning_signals=active_warning_signals,
    recommendations=recommendations,
    model_available_for_record=model_available_for_record,
    current_assessment=current_assessment,
    document_result=document_result,
    data_intelligence=data_intelligence,
    financial_columns=financial_columns,
    portfolio_analysis=portfolio_analysis,
    upload_pipeline_key=upload_pipeline_key,
    upload_signature=upload_signature,
    analysis_revision=analysis_revision,
    uploaded=uploaded,
    dataset_key=dataset_key,
    bundle=bundle,
    selected_company=str(selected_company),
    page=page,
)

if page == "Home":
    home.render(ctx)
elif page == "MSME Financial Health":
    financial_health.render(ctx)
elif page == "Risk Prediction":
    risk_prediction.render(ctx)
elif page == "Early-Warning Indicators":
    early_warning.render(ctx)
elif page == "Data Intelligence":
    data_intelligence_page.render(ctx)
elif page == "AI Assistant":
    ai_assistant.render(ctx)
elif page == "Reports":
    reports.render(ctx)
elif page == "Methodology":
    methodology.render(ctx)
elif page == "About":
    about.render(ctx)
else:
    st.stop()
