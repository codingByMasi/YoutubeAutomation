"""Streamlit error panel: shows an error with a plain title and buttons that fix or retry it inside the app."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from studio.web import remedies as rem
from studio.web import service as svc


def error_panel(error: str, *, key: str, ctx=None, log: str = "", retry: Callable[[], svc.Outcome] | None = None,
                retry_draft: Callable[[], svc.Outcome] | None = None,
                retry_force: Callable[[], svc.Outcome] | None = None) -> svc.Outcome | None:
    """Render `error` with fix buttons. Returns the Outcome of a retry if one was run this pass, else None.

    `retry` re-runs the failed action; `retry_draft`/`retry_force` are optional variants. Buttons whose callable
    is missing are hidden, so every page can use this with whatever it can re-run.
    """
    dx = rem.diagnose(error, can_retry=retry is not None)
    st.error(f"❌ {dx.title}\n\n{error}")
    funcs = {rem.RETRY: retry, rem.RETRY_DRAFT: retry_draft, rem.RETRY_FORCE: retry_force}
    shown = [r for r in dx.remedies if r not in funcs or funcs[r] is not None]
    cols = st.columns(len(shown) or 1)
    outcome: svc.Outcome | None = None
    for col, r in zip(cols, shown, strict=False):
        if not col.button(rem.LABELS[r], key=f"fix_{key}_{r}"):
            continue
        if r == rem.OPEN_SETUP:
            st.session_state["nav"] = "Setup"
            st.rerun()
        elif r == rem.COPY_REPORT:
            st.code(rem.report(error, log), language="text", wrap_lines=True)
        elif r == rem.TEST_KEYS and ctx is not None:
            res = rem.test_keys(ctx.settings)
            (st.success if res.ok else st.error)(res.message)
        elif r == rem.RELEASE_LOCK and ctx is not None:
            res = rem.release_db_lock(ctx.settings.db_path)
            (st.info if res.ok else st.error)(res.message)
            if res.ok and retry is not None:
                with st.spinner("Retrying..."):
                    outcome = retry()
        elif r in funcs and funcs[r] is not None:
            with st.spinner("Retrying..."):
                outcome = funcs[r]()
        elif r == rem.RECHECK and retry is not None:
            outcome = retry()
        if outcome is not None:
            (st.success("✅ Fixed. The step now works.") if outcome.ok else st.warning(
                "Still failing: " + outcome.error.splitlines()[0] if outcome.error else "Still failing."))
    if log.strip():
        with st.expander("Details"):
            st.code(log)
    return outcome
