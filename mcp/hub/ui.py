"""
ui.py – Streamlit dashboard for the Local MCP Hub.

Launches a browser-based control panel that lets you:
  • View hub status and connector health
  • Browse and edit files interactively
  • Query SQLite databases with a visual interface
  • Inspect Git repository history and diffs
  • Run allow-listed shell commands
  • Tune .env settings live

Run
---
    streamlit run ui.py

Requirements
------------
    pip install streamlit
    (all other deps already in requirements.txt)
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from datetime import datetime

import streamlit as st

# ── Ensure hub/ is on sys.path ────────────────────────────────────────────────
_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# ─────────────────────────────────────────────────────────────────────────────
# Page configuration (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Local MCP Hub",
    page_icon="🔌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Global CSS – dark glassmorphism theme
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
/* ── Google Fonts ───────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Root palette ────────────────────────────────────────────────────────── */
:root {
    --bg-deep:    #0a0b10;
    --bg-card:    rgba(22, 24, 38, 0.85);
    --bg-glass:   rgba(255,255,255,0.04);
    --accent1:    #7c6ff7;
    --accent2:    #5eeaff;
    --accent3:    #ff6b9d;
    --success:    #34d399;
    --warning:    #fbbf24;
    --error:      #f87171;
    --text-main:  #e2e8f0;
    --text-muted: #64748b;
    --border:     rgba(124,111,247,0.2);
}

/* ── Base ────────────────────────────────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg-deep) !important;
    font-family: 'Inter', sans-serif !important;
    color: var(--text-main) !important;
}

[data-testid="stSidebar"] {
    background: rgba(10, 11, 20, 0.97) !important;
    border-right: 1px solid var(--border) !important;
}

/* ── Sidebar title ───────────────────────────────────────────────────────── */
.sidebar-brand {
    padding: 1.2rem 0 0.5rem;
    text-align: center;
}
.sidebar-brand h1 {
    font-size: 1.25rem;
    font-weight: 700;
    background: linear-gradient(135deg, var(--accent1), var(--accent2));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
    letter-spacing: -0.02em;
}
.sidebar-brand p {
    font-size: 0.7rem;
    color: var(--text-muted);
    margin: 0.2rem 0 0;
}

/* ── Radio nav buttons ───────────────────────────────────────────────────── */
[data-testid="stRadio"] > div {
    gap: 0.25rem !important;
}
[data-testid="stRadio"] label {
    background: var(--bg-glass);
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 0.55rem 1rem;
    cursor: pointer;
    transition: all 0.2s ease;
    font-size: 0.88rem;
    font-weight: 500;
    color: var(--text-muted) !important;
    width: 100%;
}
[data-testid="stRadio"] label:hover {
    background: rgba(124,111,247,0.12);
    border-color: var(--border);
    color: var(--text-main) !important;
}
[data-testid="stRadio"] [aria-checked="true"] + label,
[data-testid="stRadio"] label[data-checked="true"] {
    background: linear-gradient(135deg, rgba(124,111,247,0.25), rgba(94,234,255,0.1));
    border-color: var(--accent1);
    color: var(--text-main) !important;
}

/* ── Metric cards ────────────────────────────────────────────────────────── */
.metric-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 1.25rem 1.5rem;
    backdrop-filter: blur(12px);
    position: relative;
    overflow: hidden;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.metric-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(124,111,247,0.15);
}
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--accent1), var(--accent2));
}
.metric-card .mc-label {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.4rem;
}
.metric-card .mc-value {
    font-size: 2rem;
    font-weight: 700;
    color: var(--text-main);
    line-height: 1.1;
}
.metric-card .mc-sub {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 0.2rem;
}

/* ── Status pills ────────────────────────────────────────────────────────── */
.pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.25rem 0.75rem;
    border-radius: 100px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.02em;
}
.pill-green  { background: rgba(52,211,153,0.15); color: var(--success); border: 1px solid rgba(52,211,153,0.3); }
.pill-yellow { background: rgba(251,191,36,0.15);  color: var(--warning); border: 1px solid rgba(251,191,36,0.3); }
.pill-red    { background: rgba(248,113,113,0.15); color: var(--error);   border: 1px solid rgba(248,113,113,0.3); }
.pill-blue   { background: rgba(124,111,247,0.15); color: var(--accent1); border: 1px solid rgba(124,111,247,0.3); }

/* ── Section headers ─────────────────────────────────────────────────────── */
.section-header {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 1.25rem;
}
.section-header h2 {
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--text-main);
    margin: 0;
}
.section-header .icon {
    font-size: 1.4rem;
    line-height: 1;
}

/* ── Panel / glass card ──────────────────────────────────────────────────── */
.panel {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    backdrop-filter: blur(12px);
}

/* ── Connector row ───────────────────────────────────────────────────────── */
.connector-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.85rem 1rem;
    background: var(--bg-glass);
    border: 1px solid var(--border);
    border-radius: 12px;
    margin-bottom: 0.5rem;
    transition: all 0.2s ease;
}
.connector-row:hover { background: rgba(124,111,247,0.06); }
.connector-row .cr-left { display: flex; align-items: center; gap: 0.75rem; }
.connector-row .cr-name { font-weight: 600; font-size: 0.92rem; }
.connector-row .cr-tools { font-size: 0.75rem; color: var(--text-muted); margin-top: 0.1rem; }

/* ── Code / output areas ─────────────────────────────────────────────────── */
.code-output {
    background: #0d0f1a;
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1rem 1.2rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    color: var(--accent2);
    max-height: 420px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-all;
}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
.stButton > button {
    background: linear-gradient(135deg, var(--accent1), #5b5bd6) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    padding: 0.55rem 1.2rem !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 4px 15px rgba(124,111,247,0.3) !important;
}
.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(124,111,247,0.45) !important;
}

/* ── Inputs & selects ────────────────────────────────────────────────────── */
.stTextInput input, .stTextArea textarea, .stSelectbox select {
    background: rgba(15, 17, 30, 0.9) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    color: var(--text-main) !important;
    font-family: 'Inter', sans-serif !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--accent1) !important;
    box-shadow: 0 0 0 2px rgba(124,111,247,0.2) !important;
}

/* ── Tabs ────────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: var(--bg-glass);
    border-radius: 12px;
    padding: 4px;
    gap: 4px;
    border: 1px solid var(--border);
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    font-size: 0.85rem;
    color: var(--text-muted) !important;
}
.stTabs [aria-selected="true"] {
    background: rgba(124,111,247,0.2) !important;
    color: var(--text-main) !important;
}

/* ── Divider ─────────────────────────────────────────────────────────────── */
hr { border-color: var(--border) !important; }

/* ── Alert boxes ─────────────────────────────────────────────────────────── */
.stSuccess, .stError, .stWarning, .stInfo {
    border-radius: 12px !important;
    font-family: 'Inter', sans-serif !important;
}

/* ── Dataframe ───────────────────────────────────────────────────────────── */
.stDataFrame {
    border-radius: 12px !important;
    overflow: hidden;
    border: 1px solid var(--border) !important;
}

/* ── File tree item ──────────────────────────────────────────────────────── */
.file-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.45rem 0.75rem;
    border-radius: 8px;
    cursor: pointer;
    font-size: 0.85rem;
    transition: background 0.15s ease;
    font-family: 'JetBrains Mono', monospace;
}
.file-item:hover { background: rgba(124,111,247,0.1); }
.file-item.is-dir { color: var(--accent2); font-weight: 600; }
.file-item.is-file { color: var(--text-muted); }

/* ── Page header ─────────────────────────────────────────────────────────── */
.page-header {
    padding: 0.5rem 0 1.5rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1.5rem;
}
.page-header h1 {
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--text-main);
    margin: 0 0 0.25rem;
}
.page-header p {
    font-size: 0.875rem;
    color: var(--text-muted);
    margin: 0;
}

/* ── Git commit card ─────────────────────────────────────────────────────── */
.commit-card {
    padding: 0.75rem 1rem;
    background: var(--bg-glass);
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 0.4rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    color: var(--text-muted);
}
.commit-card .ch { color: var(--warning); }
.commit-card .cm { color: var(--text-main); }

/* ── Scrollbar ───────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(124,111,247,0.3); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(124,111,247,0.5); }
</style>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Lazy imports – so the UI loads even if connectors have missing deps
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def _load_config():
    try:
        from mcp_hub.config import settings
        return settings, None
    except Exception as e:
        return None, str(e)


@st.cache_resource(show_spinner=False)
def _load_registry():
    try:
        from mcp_hub.permissions import load_default_permissions
        from mcp_hub.hub import build_hub
        from mcp_hub.registry import summary as reg_summary
        load_default_permissions()
        build_hub()
        return reg_summary(), None
    except Exception as e:
        return {}, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run_tool(fn, *args, **kwargs):
    """Call a connector function and return (result, error_str)."""
    try:
        return fn(*args, **kwargs), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def pill(label: str, kind: str = "blue") -> str:
    dot = {"green": "●", "yellow": "●", "red": "●", "blue": "●"}.get(kind, "●")
    return f'<span class="pill pill-{kind}">{dot} {label}</span>'


def _fmt_size(n: int | None) -> str:
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar navigation
# ─────────────────────────────────────────────────────────────────────────────

settings, cfg_err = _load_config()
reg, reg_err = _load_registry()

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <h1>⚡ Local MCP Hub</h1>
            <p>100% local · zero-cost · open source</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("---")

    page = st.radio(
        "Navigation",
        options=[
            "🏠  Dashboard",
            "📁  File Explorer",
            "🗄️  Database",
            "🔀  Git",
            "💻  Shell",
            "⚙️  Settings",
        ],
        label_visibility="collapsed",
    )
    st.markdown("---")

    # Hub status badge
    if cfg_err:
        st.markdown(pill("Hub Error", "red"), unsafe_allow_html=True)
    else:
        st.markdown(pill("Hub Ready", "green"), unsafe_allow_html=True)

    st.caption(f"v{settings.server_version if settings else '?'}")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════
if page == "🏠  Dashboard":
    st.markdown(
        """
        <div class="page-header">
            <h1>🏠 Dashboard</h1>
            <p>Hub status, loaded connectors, and quick tool overview</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if cfg_err:
        st.error(f"Failed to load config: {cfg_err}")
        st.stop()

    # ── Metric row ────────────────────────────────────────────────────────────
    all_tools = sum(len(v) for v in reg.values())
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(
            f"""<div class="metric-card">
                <div class="mc-label">Connectors</div>
                <div class="mc-value">{len(reg)}</div>
                <div class="mc-sub">loaded & active</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""<div class="metric-card">
                <div class="mc-label">Total Tools</div>
                <div class="mc-value">{all_tools}</div>
                <div class="mc-sub">registered in hub</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""<div class="metric-card">
                <div class="mc-label">Auth</div>
                <div class="mc-value" style="font-size:1.4rem">{'🔒 On' if settings.auth_enabled else '🔓 Off'}</div>
                <div class="mc-sub">{'token required' if settings.auth_enabled else 'dev mode'}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""<div class="metric-card">
                <div class="mc-label">Shell</div>
                <div class="mc-value" style="font-size:1.4rem">{'✅ On' if settings.shell_enabled else '🚫 Off'}</div>
                <div class="mc-sub">{'enabled' if settings.shell_enabled else 'disabled'}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Connector cards ───────────────────────────────────────────────────────
    st.markdown("### 🔌 Active Connectors")

    CONNECTOR_META = {
        "filesystem":  ("📁", "File system read/write"),
        "sqlite":      ("🗄️", "SQLite database"),
        "postgresql":  ("🐘", "PostgreSQL database"),
        "git":         ("🔀", "Git repository tools"),
        "shell":       ("💻", "Shell command runner"),
    }

    if not reg:
        st.warning("No connectors registered. Check your .env configuration.")
    else:
        for name, tools in reg.items():
            icon, desc = CONNECTOR_META.get(name, ("🔧", name))
            st.markdown(
                f"""<div class="connector-row">
                    <div class="cr-left">
                        <span style="font-size:1.4rem">{icon}</span>
                        <div>
                            <div class="cr-name">{name}</div>
                            <div class="cr-tools">{desc} &nbsp;·&nbsp; {len(tools)} tools: {", ".join(f"<code>{t}</code>" for t in tools)}</div>
                        </div>
                    </div>
                    <span class="pill pill-green">● Active</span>
                </div>""",
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Allowed paths ─────────────────────────────────────────────────────────
    st.markdown("### 🛡️ Sandbox – Allowed Paths")
    allowed = settings.get_allowed_paths()
    for p in allowed:
        exists = p.exists()
        badge = pill("exists", "green") if exists else pill("missing", "red")
        st.markdown(
            f"<div class='connector-row'>"
            f"<span style='font-family:JetBrains Mono,monospace;font-size:0.85rem'>{p}</span>"
            f"{badge}</div>",
            unsafe_allow_html=True,
        )


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: FILE EXPLORER
# ═════════════════════════════════════════════════════════════════════════════
elif page == "📁  File Explorer":
    st.markdown(
        """<div class="page-header">
            <h1>📁 File Explorer</h1>
            <p>Browse, read, write, search, and manage local files</p>
        </div>""",
        unsafe_allow_html=True,
    )

    try:
        from connectors.filesystem import register as _fs_reg  # noqa: F401
        from mcp_hub.sandbox import validate_path, SandboxError
    except ImportError as e:
        st.error(f"Filesystem connector unavailable: {e}")
        st.stop()

    tab_browse, tab_read, tab_write, tab_search = st.tabs(
        ["📂 Browse", "📖 Read File", "✏️ Write File", "🔍 Search"]
    )

    # ── Browse ────────────────────────────────────────────────────────────────
    with tab_browse:
        default_path = str(settings.get_allowed_paths()[0]) if settings else "."
        dir_path = st.text_input("Directory path", value=default_path, key="fs_browse_path")

        if st.button("List Directory", key="fs_list_btn"):
            try:
                p = validate_path(dir_path, must_exist=True)
                entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
                rows = []
                for e in entries:
                    try:
                        size = e.stat().st_size if e.is_file() else None
                    except OSError:
                        size = None
                    kind = "📁" if e.is_dir() else "📄"
                    rows.append({
                        "Type": kind,
                        "Name": e.name,
                        "Kind": "Directory" if e.is_dir() else "File",
                        "Size": _fmt_size(size),
                    })

                if rows:
                    import pandas as pd
                    df = pd.DataFrame(rows)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    st.caption(f"{len(rows)} items in `{p}`")
                else:
                    st.info("Directory is empty.")
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")

    # ── Read ──────────────────────────────────────────────────────────────────
    with tab_read:
        file_path = st.text_input("File path", key="fs_read_path",
                                   placeholder="/path/to/your/file.txt")
        if st.button("Read File", key="fs_read_btn"):
            try:
                from mcp_hub.sandbox import validate_path, check_file_size
                r = validate_path(file_path, must_exist=True)
                check_file_size(r)
                content = r.read_text(encoding="utf-8", errors="replace")
                lines = content.count("\n") + 1
                chars = len(content)
                c1, c2 = st.columns(2)
                c1.metric("Lines", f"{lines:,}")
                c2.metric("Characters", f"{chars:,}")
                lang = r.suffix.lstrip(".") or "text"
                st.code(content, language=lang)
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")

    # ── Write ─────────────────────────────────────────────────────────────────
    with tab_write:
        wpath = st.text_input("File path", key="fs_write_path",
                               placeholder="/path/to/output.txt")
        wcontent = st.text_area("Content", height=300, key="fs_write_content",
                                 placeholder="Type or paste file content here…")
        if st.button("Write File", key="fs_write_btn"):
            try:
                from mcp_hub.sandbox import validate_path
                import stat as _stat
                r = validate_path(wpath)
                if r.exists() and not (r.stat().st_mode & _stat.S_IWRITE):
                    st.error(f"'{r}' is read-only.")
                else:
                    r.parent.mkdir(parents=True, exist_ok=True)
                    n = r.write_text(wcontent, encoding="utf-8")
                    st.success(f"✓ Wrote {n:,} bytes to `{r}`")
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")

    # ── Search ────────────────────────────────────────────────────────────────
    with tab_search:
        sroot = st.text_input("Search root directory", key="fs_search_root",
                               value=str(settings.get_allowed_paths()[0]) if settings else ".")
        spattern = st.text_input("Glob pattern", value="**/*.py", key="fs_search_pattern",
                                  help="Examples: **/*.txt, *.md, src/**/*.js")
        if st.button("Search", key="fs_search_btn"):
            try:
                from mcp_hub.sandbox import validate_path
                r = validate_path(sroot, must_exist=True)
                results = sorted(r.glob(spattern))
                files = [p for p in results if p.is_file()]
                if files:
                    import pandas as pd
                    df = pd.DataFrame([{
                        "Path": str(f.relative_to(r)),
                        "Size": _fmt_size(f.stat().st_size),
                        "Modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                    } for f in files[:500]])
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    st.caption(f"Found {len(files)} file(s) matching `{spattern}`")
                else:
                    st.info("No files matched.")
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: DATABASE
# ═════════════════════════════════════════════════════════════════════════════
elif page == "🗄️  Database":
    st.markdown(
        """<div class="page-header">
            <h1>🗄️ Database</h1>
            <p>Query SQLite databases with an interactive SQL editor</p>
        </div>""",
        unsafe_allow_html=True,
    )

    tab_query, tab_tables, tab_schema, tab_exec = st.tabs(
        ["🔍 Query", "📋 Tables", "📐 Schema", "✏️ Execute"]
    )

    def _sqlite_conn():
        import sqlite3
        db = settings.sqlite_db_path if settings else ""
        if not db:
            raise ValueError("SQLITE_DB_PATH is not configured. Add it to your .env file.")
        p = Path(db).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Database not found: {p}")
        conn = sqlite3.connect(str(p), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    with tab_query:
        sql = st.text_area(
            "SQL Query (SELECT only)",
            height=180,
            value="SELECT * FROM sqlite_master WHERE type='table' LIMIT 20;",
            key="db_sql",
            help="Only SELECT statements. Use the Execute tab for writes.",
        )
        if st.button("Run Query", key="db_run_btn"):
            try:
                import pandas as pd
                conn = _sqlite_conn()
                cur = conn.execute(sql)
                rows = [dict(r) for r in cur.fetchall()]
                conn.close()
                if rows:
                    df = pd.DataFrame(rows)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    st.caption(f"{len(rows)} row(s) returned")
                else:
                    st.info("Query returned no rows.")
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")

    with tab_tables:
        if st.button("List Tables", key="db_tables_btn"):
            try:
                conn = _sqlite_conn()
                cur = conn.execute(
                    "SELECT name, sql FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
                rows = cur.fetchall()
                conn.close()
                if rows:
                    for r in rows:
                        st.markdown(
                            f"<div class='connector-row'>"
                            f"<span style='font-family:JetBrains Mono,monospace'>{r[0]}</span>"
                            f"{pill('table', 'blue')}</div>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.info("No user-defined tables found.")
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")

    with tab_schema:
        tbl = st.text_input("Table name", key="db_schema_tbl")
        if st.button("Get Schema", key="db_schema_btn"):
            try:
                conn = _sqlite_conn()
                cur = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
                )
                row = cur.fetchone()
                conn.close()
                if row:
                    st.code(row[0], language="sql")
                else:
                    st.error(f"Table '{tbl}' not found.")
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")

    with tab_exec:
        st.warning("⚠️ This tab runs write SQL (INSERT / UPDATE / DELETE / DDL). Use with care.")
        wsql = st.text_area("SQL Statement", height=180, key="db_exec_sql",
                             placeholder="CREATE TABLE example (id INTEGER PRIMARY KEY, name TEXT);")
        if st.button("Execute", key="db_exec_btn"):
            try:
                conn = _sqlite_conn()
                cur = conn.execute(wsql)
                conn.commit()
                st.success(f"✓ Executed. Rows affected: {cur.rowcount} · Last row ID: {cur.lastrowid}")
                conn.close()
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: GIT
# ═════════════════════════════════════════════════════════════════════════════
elif page == "🔀  Git":
    st.markdown(
        """<div class="page-header">
            <h1>🔀 Git</h1>
            <p>Inspect repository history, diffs, and branches</p>
        </div>""",
        unsafe_allow_html=True,
    )

    git_root_default = settings.git_root if (settings and settings.git_root) else str(Path.cwd())
    repo_path = st.text_input("Repository path", value=git_root_default, key="git_repo")

    def _git(args, cwd):
        import subprocess
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or f"git {args[0]} failed")
        return r.stdout.strip()

    tab_status, tab_log, tab_diff, tab_branches, tab_commit = st.tabs(
        ["📊 Status", "📜 Log", "🔍 Diff", "🌿 Branches", "✅ Commit"]
    )

    with tab_status:
        if st.button("Refresh Status", key="git_status_btn"):
            try:
                out = _git(["status", "--short", "--branch"], repo_path)
                st.markdown(f"<div class='code-output'>{out or '(clean working tree)'}</div>",
                            unsafe_allow_html=True)
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")

    with tab_log:
        n = st.slider("Number of commits", 5, 50, 15, key="git_log_n")
        if st.button("Show Log", key="git_log_btn"):
            try:
                out = _git(["log", f"-{n}", "--oneline", "--decorate", "--graph"], repo_path)
                st.markdown(f"<div class='code-output'>{out or '(no commits)'}</div>",
                            unsafe_allow_html=True)
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")

    with tab_diff:
        staged = st.checkbox("Show staged diff (--cached)", key="git_staged")
        if st.button("Show Diff", key="git_diff_btn"):
            try:
                args = ["diff"] + (["--cached"] if staged else [])
                out = _git(args, repo_path)
                out = out[:65536] if out else "(no changes)"
                st.code(out, language="diff")
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")

    with tab_branches:
        if st.button("List Branches", key="git_branch_btn"):
            try:
                out = _git(["branch", "-v"], repo_path)
                st.markdown(f"<div class='code-output'>{out or '(no branches)'}</div>",
                            unsafe_allow_html=True)
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")

    with tab_commit:
        st.warning("⚠️ This will create a real git commit in the selected repository.")
        files_to_add = st.text_input("Files to stage (space-separated, '.' for all)",
                                      value=".", key="git_add_paths")
        commit_msg = st.text_area("Commit message", height=100, key="git_msg")
        c1, c2 = st.columns(2)
        if c1.button("Stage Files", key="git_add_btn"):
            try:
                out = _git(["add", "--verbose", "--"] + files_to_add.split(), repo_path)
                st.success(out or f"✓ Staged: {files_to_add}")
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")
        if c2.button("Commit", key="git_commit_btn"):
            if not commit_msg.strip():
                st.error("Commit message is required.")
            else:
                try:
                    out = _git(["commit", "-m", commit_msg.strip()], repo_path)
                    st.success(f"✓ {out}")
                except Exception as e:
                    st.error(f"{type(e).__name__}: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: SHELL
# ═════════════════════════════════════════════════════════════════════════════
elif page == "💻  Shell":
    st.markdown(
        """<div class="page-header">
            <h1>💻 Shell</h1>
            <p>Run allow-listed commands securely</p>
        </div>""",
        unsafe_allow_html=True,
    )

    if settings and not settings.shell_enabled:
        st.warning(
            "🚫 Shell connector is disabled.  "
            "Set `SHELL_ENABLED=true` in your `.env` to enable it."
        )

    allowed_cmds = settings.get_allowed_commands() if settings else []
    st.markdown(
        "**Allow-listed commands:** " +
        " ".join(f"`{c}`" for c in allowed_cmds),
    )

    cmd = st.text_input("Command", placeholder="python --version", key="shell_cmd")
    cwd_shell = st.text_input(
        "Working directory (optional)",
        value=str(settings.get_allowed_paths()[0]) if settings else str(Path.cwd()),
        key="shell_cwd",
    )

    if st.button("Run Command", key="shell_run_btn", disabled=not (settings and settings.shell_enabled)):
        if not cmd.strip():
            st.error("Enter a command.")
        else:
            first = cmd.strip().split()[0].lower()
            if first not in [c.lower() for c in allowed_cmds]:
                st.error(
                    f"'{first}' is not in the allow-list.  "
                    f"Allowed: {', '.join(sorted(allowed_cmds))}"
                )
            else:
                import subprocess
                try:
                    r = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True,
                        cwd=cwd_shell,
                        timeout=settings.shell_timeout_seconds if settings else 30,
                    )
                    c1, c2 = st.columns([3, 1])
                    c1.metric("Return code", r.returncode)
                    if r.stdout:
                        st.markdown("**stdout**")
                        st.markdown(
                            f"<div class='code-output'>{r.stdout[:16384]}</div>",
                            unsafe_allow_html=True,
                        )
                    if r.stderr:
                        st.markdown("**stderr**")
                        st.markdown(
                            f"<div class='code-output' style='color:var(--error)'>"
                            f"{r.stderr[:4096]}</div>",
                            unsafe_allow_html=True,
                        )
                except subprocess.TimeoutExpired:
                    st.error(f"Command timed out after {settings.shell_timeout_seconds}s.")
                except Exception as e:
                    st.error(f"{type(e).__name__}: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: SETTINGS
# ═════════════════════════════════════════════════════════════════════════════
elif page == "⚙️  Settings":
    st.markdown(
        """<div class="page-header">
            <h1>⚙️ Settings</h1>
            <p>Current hub configuration (read from .env)</p>
        </div>""",
        unsafe_allow_html=True,
    )

    if cfg_err or not settings:
        st.error(f"Could not load settings: {cfg_err}")
        st.stop()

    env_path = _HERE / ".env"
    example_path = _HERE / ".env.example"

    # ── Config display ────────────────────────────────────────────────────────
    st.markdown("### Current Configuration")

    cfg_rows = {
        "Server Name":       settings.server_name,
        "Server Version":    settings.server_version,
        "Log Level":         settings.log_level,
        "Auth Enabled":      str(settings.auth_enabled),
        "Auth Tokens":       "●●●●●●●●" if settings.auth_tokens else "(not set)",
        "Allowed Paths":     settings.allowed_paths or "(CWD default)",
        "SQLite DB Path":    settings.sqlite_db_path or "(disabled)",
        "Postgres URL":      "●●●●●●●●" if settings.postgres_url else "(disabled)",
        "Git Root":          settings.git_root or "(disabled)",
        "Shell Enabled":     str(settings.shell_enabled),
        "Shell Commands":    settings.shell_allowed_commands,
        "Shell Timeout":     f"{settings.shell_timeout_seconds}s",
        "Max File Size":     _fmt_size(settings.max_file_size_bytes),
        "Max Output Rows":   str(settings.max_output_rows),
        "Tool Timeout":      f"{settings.tool_timeout_seconds}s",
    }

    import pandas as pd
    df = pd.DataFrame(
        [{"Setting": k, "Value": v} for k, v in cfg_rows.items()]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── .env editor ───────────────────────────────────────────────────────────
    st.markdown("### Edit .env File")

    if not env_path.exists() and example_path.exists():
        st.info(".env not found — showing .env.example. Click 'Save as .env' to create it.")
        existing = example_path.read_text(encoding="utf-8")
    elif env_path.exists():
        existing = env_path.read_text(encoding="utf-8")
    else:
        existing = "# No .env.example found.\nSERVER_NAME=local-mcp-hub\nLOG_LEVEL=INFO\n"

    new_content = st.text_area(".env content", value=existing, height=400, key="settings_env_content")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save .env", key="settings_save_btn"):
            try:
                env_path.write_text(new_content, encoding="utf-8")
                st.success(f"✓ Saved to `{env_path}`  •  Restart the hub to apply changes.")
                st.cache_resource.clear()
            except Exception as e:
                st.error(f"Failed to save: {e}")

    with col2:
        if st.button("🔑 Generate New Token", key="settings_token_btn"):
            import secrets
            token = secrets.token_hex(32)
            st.code(token, language="text")
            st.caption("Copy this token into AUTH_TOKENS in your .env")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Quick-start guide ─────────────────────────────────────────────────────
    with st.expander("📋 Quick MCP Client Configuration"):
        abs_main = str(_HERE / "main.py")
        st.markdown("**Claude Desktop** – paste into `claude_desktop_config.json`:")
        st.code(
            f'{{\n  "mcpServers": {{\n    "local-mcp-hub": {{\n'
            f'      "command": "python",\n'
            f'      "args": ["{abs_main}"]\n'
            f"    }}\n  }}\n}}",
            language="json",
        )
        st.markdown("**Cursor** – paste into `~/.cursor/mcp.json`:")
        st.code(
            f'{{\n  "mcpServers": {{\n    "local-mcp-hub": {{\n'
            f'      "command": "python",\n'
            f'      "args": ["{abs_main}"]\n'
            f"    }}\n  }}\n}}",
            language="json",
        )
