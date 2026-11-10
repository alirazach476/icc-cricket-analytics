# ruff: noqa: E501
"""A tiny stand-in for the ``streamlit`` module.

The dashboard pages in ``app/pages`` are written against the Streamlit API. Rather than
re-implement every chart a second time, the React front end runs those very same page
scripts through this shim: each ``st.*`` call is recorded as a JSON node (tab, column,
metric, Plotly figure, table, widget ...) and the React app renders the resulting tree.

Widgets work like Streamlit's: the client posts the current widget values, the page is
re-run, and every widget returns the posted value (or its default).
"""

from __future__ import annotations

import copy
import json
import math
import sys
import types
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd
import plotly.io as pio


class StopRun(Exception):
    """Raised by ``st.stop()``."""


# --------------------------------------------------------------------------- wording per competition
# The page scripts are written for the World Cups; other competitions get the same sentences with their own name.
LOCAL_WORDS = {
    "ct": [
        ("ODI data starts at the 2003 World Cup, so career records cover 2003-2023 only.", ""),
        (
            "Super-stage tables (Super Six / Super Eight) include results carried over from the first round, as in the source.",
            "",
        ),
        ("World Cups", "Champions Trophies"),
        ("World Cup", "Champions Trophy"),
    ],
    "asia": [
        ("ODI data starts at the 2003 World Cup, so career records cover 2003-2023 only.", ""),
        (
            "Super-stage tables (Super Six / Super Eight) include results carried over from the first round, as in the source.",
            "",
        ),
        ("World Cups", "Asia Cups"),
        ("World Cup", "Asia Cup"),
    ],
    "wtc": [
        ("ODI data starts at the 2003 World Cup, so career records cover 2003-2023 only.", ""),
        (
            "Super-stage tables (Super Six / Super Eight) include results carried over from the first round, as in the source.",
            "",
        ),
        ("World Cups", "WTC editions"),
        ("World Cup", "WTC cycle"),
    ],
}


def local(text: Any) -> Any:
    """Re-word a text for the competition being shown (identity for the World Cups)."""
    code = getattr(CTX, "competition", "wc")
    if not isinstance(text, str) or code not in LOCAL_WORDS:
        return text
    for old, new in LOCAL_WORDS[code]:
        text = text.replace(old, new)
    return text


# --------------------------------------------------------------------------- JSON helpers
def jsonable(v: Any) -> Any:
    """Convert numpy / pandas / date values into plain JSON values."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return str(v)[:19] if isinstance(v, (pd.Timestamp, datetime)) else str(v)
    if v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, (str, int, bool)):
        return v
    return str(v)


HIDDEN_COLUMNS = {"is_synthetic", "generator_version", "seed"}


def frame_to_json(df: Any, limit: int = 3000, column_order: list[str] | None = None) -> dict:
    if hasattr(df, "data") and isinstance(getattr(df, "data", None), pd.DataFrame):  # Styler
        df = df.data
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if not isinstance(df.index, pd.RangeIndex):
        # an unnamed index is just row ids; a named one (e.g. a group key) is real data
        named = any(n is not None for n in df.index.names)
        df = df.reset_index(drop=not named)
    df = df.head(limit).copy()
    df.columns = [str(c) for c in df.columns]
    links = None
    if "match_id" in df.columns:  # rows become clickable: they open the match detail
        links = [None if v is None or v != v else str(v) for v in df["match_id"].tolist()]
    if column_order:
        df = df[[c for c in column_order if c in df.columns]]
    df = df.drop(columns=[c for c in df.columns if c == "match_id" or c in HIDDEN_COLUMNS])
    cols = list(df.columns)
    numeric = [
        bool(pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c]))
        for c in cols
    ]
    rows = [[jsonable(x) for x in r] for r in df.itertuples(index=False, name=None)]
    return {"columns": cols, "numeric": numeric, "rows": rows, "total": len(rows), "links": links}


def figure_to_json(fig: Any) -> dict:
    from app.utils import theme

    try:
        theme.wrap_title(fig)
    except Exception:  # noqa: BLE001 - styling must never break a page
        pass
    d = json.loads(pio.to_json(fig))
    lay = d.setdefault("layout", {})
    lay.pop("template", None)  # the client applies the shared template once
    title = lay.get("title") or {}
    if title.get("text"):
        title["text"] = local(
            title["text"]
        )  # keep (wrapped) titles clear of the plot area and the legend
        lines = str(title["text"]).count("<br>") + 1
        margin = lay.setdefault("margin", {})
        margin["t"] = max(int(margin.get("t") or 0), 96 if lines > 1 else 80)
        title.update({"y": 0.97, "yref": "container", "yanchor": "top"})
        lay["title"] = title
    if any(t.get("type") == "pie" for t in d.get("data", [])):
        lay["legend"] = {
            "orientation": "v",
            "x": 1.02,
            "y": 0.5,
            "yanchor": "middle",
            "xanchor": "left",
        }
    return d


# --------------------------------------------------------------------------- run context
class Ctx:
    def __init__(self, state: dict, edition: dict | None, competition: str = "wc") -> None:
        self.competition = competition
        self.state = state or {}
        self.edition = edition
        self.counts: dict[str, int] = {}
        self.sidebar = Container(sidebar=True)
        self.body = Container()
        self.stack: list[Container] = [self.body]
        self.hero: dict | None = None
        self.unsupported: set[str] = set()
        self.notes: list[str] = []
        self.session: dict = dict(self.state.get("__session") or {})


CTX: Ctx = None  # type: ignore[assignment]  (set below, after Container exists)


def _cur() -> Container:
    return CTX.stack[-1]


# --------------------------------------------------------------------------- edition defaults
def _edition_pick(label: str, kind: str, opts: list[Any]) -> int | None:
    """Index of the option the selected World Cup implies for this widget, if any."""
    ed = CTX.edition
    if not ed or not opts:
        return None
    lab = label.strip().lower()
    sopts = [str(o) for o in opts]
    if lab.startswith("format") and set(sopts) <= {"ODI", "T20"}:
        return sopts.index(ed["format"]) if ed["format"] in sopts else None
    if lab == "tournament year":
        return sopts.index(str(ed["year"])) if str(ed["year"]) in sopts else None
    if lab == "tournament":
        return sopts.index(ed["name"]) if ed["name"] in sopts else None
    return None


def _edition_filter(label: str, opts: list[Any]) -> list[Any]:
    """Match pickers (labels starting with a date) are narrowed to the selected World Cup."""
    ed = CTX.edition
    if not ed or not label.strip().lower().startswith("match"):
        return opts
    lo, hi = ed["start"], ed["end"]
    kept = [o for o in opts if isinstance(o, str) and lo <= o[:10] <= hi]
    if not kept:
        CTX.notes.append(
            f"No matches in this list belong to {ed['name']}, so all matches are shown."
        )
    return kept or opts


# --------------------------------------------------------------------------- containers
class Container:
    def __init__(self, sidebar: bool = False) -> None:
        self.nodes: list[dict] = []
        self.sidebar = sidebar

    # ---- context manager
    def __enter__(self) -> Container:
        CTX.stack.append(self)
        return self

    def __exit__(self, *exc: Any) -> bool:
        CTX.stack.pop()
        return False

    def _add(self, node: dict) -> dict:
        self.nodes.append(node)
        return node

    # ---- layout
    def tabs(self, labels: list[str]) -> list[Container]:
        items = [Container() for _ in labels]
        self._add(
            {
                "t": "tabs",
                "labels": [local(str(x)) for x in labels],
                "items": [c.nodes for c in items],
            }
        )
        return items

    def columns(self, spec: Any = 2, **_: Any) -> list[Container]:
        weights = [1] * spec if isinstance(spec, int) else [float(x) for x in spec]
        items = [Container() for _ in weights]
        self._add({"t": "cols", "w": weights, "items": [c.nodes for c in items]})
        return items

    def expander(self, label: str, expanded: bool = False, **_: Any) -> Container:
        c = Container()
        label = str(label).replace(" (SYNTHETIC demo data)", "")
        self._add({"t": "expander", "label": str(label), "open": bool(expanded), "items": c.nodes})
        return c

    def container(self, **_: Any) -> Container:
        c = Container()
        self._add({"t": "box", "items": c.nodes})
        return c

    # ---- text
    def markdown(self, body: Any, unsafe_allow_html: bool = False, **_: Any) -> None:
        text = local(str(body))
        if text.lstrip().startswith("<style"):
            return
        self._add({"t": "md", "text": text, "html": bool(unsafe_allow_html)})

    def write(self, *args: Any, **_: Any) -> None:
        for a in args:
            if isinstance(a, pd.DataFrame):
                self.dataframe(a)
            else:
                self.markdown(str(a))

    def caption(self, body: Any, **_: Any) -> None:
        if "labelled synthetic" in str(body):
            return
        self._add({"t": "caption", "text": local(str(body))})

    def subheader(self, body: Any, **_: Any) -> None:
        self._add({"t": "h3", "text": local(str(body))})

    def header(self, body: Any, **_: Any) -> None:
        self._add({"t": "h2", "text": local(str(body))})

    def title(self, body: Any, **_: Any) -> None:
        self._add({"t": "h1", "text": str(body)})

    def text(self, body: Any, **_: Any) -> None:
        self._add({"t": "md", "text": str(body), "html": False})

    def divider(self, **_: Any) -> None:
        self._add({"t": "hr"})

    def code(self, body: Any, language: str | None = "python", **_: Any) -> None:
        self._add({"t": "code", "text": str(body), "lang": language})

    def _alert(self, kind: str, body: Any, **_: Any) -> None:
        if "SYNTHETIC DEMO DATA" in str(body):
            return
        self._add({"t": "alert", "kind": kind, "text": local(str(body))})

    def info(self, body: Any, **kw: Any) -> None:
        self._alert("info", body, **kw)

    def warning(self, body: Any, **kw: Any) -> None:
        self._alert("warning", body, **kw)

    def error(self, body: Any, **kw: Any) -> None:
        self._alert("error", body, **kw)

    def success(self, body: Any, **kw: Any) -> None:
        self._alert("success", body, **kw)

    # ---- data display
    def metric(
        self, label: str, value: Any, delta: Any = None, help: str | None = None, **_: Any
    ) -> None:  # noqa: A002
        self._add(
            {
                "t": "metric",
                "label": str(label),
                "value": str(value),
                "delta": None if delta is None else str(delta),
                "help": help,
            }
        )

    def fixtures(self, data: Any) -> None:
        self._add({"t": "fixtures", "data": jsonable(data)})

    def match_centre(self, payload: Any, figs: dict | None = None) -> None:
        from app.utils.match_centre import CHART_GROUPS

        groups = []
        for g, names in CHART_GROUPS:
            items = [{"name": k, "fig": figure_to_json(figs[k])} for n in names for k in (figs or {}) if k == n or k.startswith(n + " ·")]
            if items:
                groups.append({"group": g, "figs": items})
        self._add({"t": "matchcentre", "data": jsonable(payload), "charts": groups})

    def plotly_chart(self, fig: Any, **_: Any) -> None:
        self._add({"t": "plot", "fig": figure_to_json(fig)})

    def dataframe(self, df: Any, column_order: list[str] | None = None, **_: Any) -> None:
        self._add({"t": "table", **frame_to_json(df, column_order=column_order)})

    table = dataframe

    def graphviz_chart(self, src: Any, **_: Any) -> None:
        self._add({"t": "graphviz", "src": getattr(src, "source", str(src))})

    def download_button(self, *a: Any, **k: Any) -> bool:
        return False

    def button(self, *a: Any, **k: Any) -> bool:
        return False

    # ---- widgets
    def _wid(self, kind: str, label: str, key: str | None) -> str:
        if key:
            return str(key)
        k = f"{kind}|{label}"
        CTX.counts[k] = CTX.counts.get(k, 0) + 1
        return f"{k}|{CTX.counts[k]}"

    def _choice(
        self,
        kind: str,
        label: str,
        options: Any,
        index: int | None,
        key: str | None,
        format_func: Any = None,
        value: Any = None,
        horizontal: bool = False,
        rich: Any = None,
        **_: Any,
    ) -> Any:
        opts = list(options)
        wanted = opts[index] if (index is not None and 0 <= index < len(opts)) else None
        opts = _edition_filter(label, opts)
        if wanted is not None and wanted in opts:
            index = opts.index(wanted)
        wid = self._wid(kind, label, key)
        jopts = [jsonable(o) for o in opts]
        labels = [local((str(format_func(o)) if format_func else str(o)).strip()) for o in opts]
        sel: int | None = None
        if wid in CTX.state:
            posted = CTX.state[wid]
            for i, jo in enumerate(jopts):
                if jo == posted or str(jo) == str(posted):
                    sel = i
                    break
        if sel is None:
            sel = _edition_pick(label, kind, opts)
        if sel is None and value is not None:
            for i, o in enumerate(opts):
                if o == value or jsonable(o) == jsonable(value):
                    sel = i
                    break
        if sel is None:
            sel = index if (index is not None and 0 <= index < len(opts)) else 0
        self._add(
            {
                "t": "w",
                "kind": kind,
                "id": wid,
                "label": str(label),
                "options": [{"v": jo, "l": lb} for jo, lb in zip(jopts, labels, strict=True)],
                "value": jopts[sel] if opts else None,
                "rich": ([jsonable(rich.get(o)) for o in opts] if isinstance(rich, dict) else None),
                "horizontal": bool(horizontal),
                "side": self.sidebar,
            }
        )
        return opts[sel] if opts else None

    def selectbox(
        self,
        label: str,
        options: Any,
        index: int = 0,
        key: str | None = None,
        format_func: Any = None,
        **kw: Any,
    ) -> Any:
        return self._choice("select", label, options, index, key, format_func, **kw)

    def radio(
        self,
        label: str,
        options: Any,
        index: int = 0,
        key: str | None = None,
        format_func: Any = None,
        horizontal: bool = False,
        **kw: Any,
    ) -> Any:
        return self._choice(
            "radio", label, options, index, key, format_func, horizontal=horizontal, **kw
        )

    def select_slider(
        self,
        label: str,
        options: Any = (),
        value: Any = None,
        key: str | None = None,
        format_func: Any = None,
        **kw: Any,
    ) -> Any:
        return self._choice(
            "slider_opts", label, options, None, key, format_func, value=value, **kw
        )

    def multiselect(
        self, label: str, options: Any, default: Any = None, key: str | None = None, **_: Any
    ) -> list[Any]:
        opts = list(options)
        wid = self._wid("multi", label, key)
        jopts = [jsonable(o) for o in opts]
        if wid in CTX.state and isinstance(CTX.state[wid], list):
            want = [str(x) for x in CTX.state[wid]]
        else:
            want = [str(jsonable(x)) for x in (default or [])]
        chosen = [o for o, jo in zip(opts, jopts, strict=True) if str(jo) in want]
        self._add(
            {
                "t": "w",
                "kind": "multi",
                "id": wid,
                "label": str(label),
                "options": [{"v": jo, "l": str(o)} for jo, o in zip(jopts, opts, strict=True)],
                "value": [jsonable(o) for o in chosen],
                "side": self.sidebar,
            }
        )
        return chosen

    def slider(
        self,
        label: str,
        min_value: float = 0,
        max_value: float = 100,
        value: float | None = None,
        step: float | None = None,
        key: str | None = None,
        **_: Any,
    ) -> Any:
        wid = self._wid("slider", label, key)
        v = CTX.state.get(wid, value if value is not None else min_value)
        v = min(max(v, min_value), max_value)
        if isinstance(min_value, int) and isinstance(max_value, int) and not isinstance(v, bool):
            v = int(v)
        self._add(
            {
                "t": "w",
                "kind": "slider",
                "id": wid,
                "label": str(label),
                "min": jsonable(min_value),
                "max": jsonable(max_value),
                "step": jsonable(step or 1),
                "value": jsonable(v),
                "side": self.sidebar,
            }
        )
        return v

    def checkbox(self, label: str, value: bool = False, key: str | None = None, **_: Any) -> bool:
        wid = self._wid("check", label, key)
        v = bool(CTX.state.get(wid, value))
        self._add(
            {
                "t": "w",
                "kind": "check",
                "id": wid,
                "label": str(label),
                "value": v,
                "side": self.sidebar,
            }
        )
        return v

    toggle = checkbox

    def text_input(self, label: str, value: str = "", key: str | None = None, **_: Any) -> str:
        wid = self._wid("text", label, key)
        v = str(CTX.state.get(wid, value))
        self._add(
            {
                "t": "w",
                "kind": "text",
                "id": wid,
                "label": str(label),
                "value": v,
                "side": self.sidebar,
            }
        )
        return v

    def number_input(
        self,
        label: str,
        min_value: float = 0,
        max_value: float = 1e9,
        value: float | None = None,
        step: float = 1,
        key: str | None = None,
        **_: Any,
    ) -> Any:
        return self.slider(label, min_value, max_value, value, step, key)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)

        def unsupported(*a: Any, **k: Any) -> None:
            CTX.unsupported.add(name)

        return unsupported


CTX = Ctx({}, None)


# --------------------------------------------------------------------------- caching
class _Cached:
    def __init__(self, fn: Any) -> None:
        self.fn = fn
        self.store: dict[str, Any] = {}
        self.__name__ = getattr(fn, "__name__", "cached")
        self.__doc__ = fn.__doc__

    def __call__(self, *a: Any, **k: Any) -> Any:
        key = repr((CTX.competition, a, sorted(k.items())))
        if key not in self.store:
            self.store[key] = self.fn(*a, **k)
        out = self.store[key]
        return out.copy() if isinstance(out, (pd.DataFrame, pd.Series)) else copy.deepcopy(out)

    def clear(self) -> None:
        self.store.clear()


def _cache_data(fn: Any = None, **_: Any) -> Any:
    if fn is not None and callable(fn):
        return _Cached(fn)
    return lambda f: _Cached(f)


# --------------------------------------------------------------------------- module
def install() -> types.ModuleType:
    """Register the fake ``streamlit`` module (idempotent)."""
    mod = types.ModuleType("streamlit")
    mod.__dict__["__shim__"] = True
    delegates = [
        "tabs",
        "columns",
        "expander",
        "container",
        "markdown",
        "write",
        "caption",
        "subheader",
        "header",
        "title",
        "text",
        "divider",
        "code",
        "info",
        "warning",
        "error",
        "success",
        "metric",
        "plotly_chart",
        "dataframe",
        "table",
        "graphviz_chart",
        "match_centre",
        "fixtures",
        "download_button",
        "button",
        "selectbox",
        "radio",
        "select_slider",
        "multiselect",
        "slider",
        "checkbox",
        "toggle",
        "text_input",
        "number_input",
    ]
    for name in delegates:
        mod.__dict__[name] = (lambda n: lambda *a, **k: getattr(_cur(), n)(*a, **k))(name)

    class _SidebarProxy:
        def __getattr__(self, name: str) -> Any:
            return getattr(CTX.sidebar, name)

        def __enter__(self) -> Container:
            return CTX.sidebar.__enter__()

        def __exit__(self, *e: Any) -> bool:
            return CTX.sidebar.__exit__(*e)

    class _StreamlitAPIException(Exception):
        pass

    mod.sidebar = _SidebarProxy()  # type: ignore[attr-defined]
    mod.cache_data = _cache_data  # type: ignore[attr-defined]
    mod.cache_resource = _cache_data  # type: ignore[attr-defined]
    mod.set_page_config = lambda *a, **k: None  # type: ignore[attr-defined]
    mod.errors = types.SimpleNamespace(StreamlitAPIException=_StreamlitAPIException)  # type: ignore[attr-defined]
    mod.session_state = _SessionState()  # type: ignore[attr-defined]

    def stop() -> None:
        raise StopRun

    mod.stop = stop  # type: ignore[attr-defined]
    mod.rerun = stop  # type: ignore[attr-defined]
    mod.__getattr__ = lambda name: lambda *a, **k: CTX.unsupported.add(name)  # type: ignore[attr-defined]
    sys.modules["streamlit"] = mod
    return mod


class _SessionState:
    """``st.session_state`` for one page run (seeded by the client, e.g. ``focus_match``)."""

    def get(self, key: str, default: Any = None) -> Any:
        return CTX.session.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return CTX.session[key]

    def __setitem__(self, key: str, value: Any) -> None:
        CTX.session[key] = value

    def __contains__(self, key: object) -> bool:
        return key in CTX.session

    __getattr__ = __getitem__  # type: ignore[assignment]
