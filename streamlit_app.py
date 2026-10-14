"""Streamlit Cloud entrypoint.

``app.py`` is a script (it renders on every run), so it must be *executed*
on each rerun. A plain ``import app`` only runs the module body once per
server process; every later rerun (tab click, widget change) was a silent
no-op that left the page blank for all users. ``runpy`` re-executes it.
"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "app.py"), run_name="__main__")
