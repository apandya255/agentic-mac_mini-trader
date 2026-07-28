#!/usr/bin/env python3
"""
Portfolio Dashboard Generator — v3 (Interactive SPA)

Generates a self-contained HTML dashboard that fetches live data from serve.py API.
Features: Accept/Deny pending orders, live P&L, equity curve, sidebar nav, tabbed views.

When served via serve.py, the dashboard auto-refreshes from the API.
When opened as a static file, it displays the last-known state embedded at generation time.
"""

import warnings
warnings.filterwarnings('ignore')

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/Users/akashpandya/AgenticTradingResearch/src")
from data_platform.prices import PriceService

BASE_DIR = Path("/Users/akashpandya/AgenticTradingResearch")
BOOK_PATH = BASE_DIR / "memos" / "state" / "book.json"
ORDERS_DIR = BASE_DIR / "memos" / "orders"
PROPOSALS_DIR = BASE_DIR / "memos" / "proposals"
DEBATE_DIR = BASE_DIR / "memos" / "debate"
RISK_DIR = BASE_DIR / "memos" / "risk"
SCORES_DIR = BASE_DIR / "memos" / "scores"
LOGS_DIR = BASE_DIR / "memos" / "logs"
HISTORY_PATH = BASE_DIR / "memos" / "state" / "pnl_history.json"
OUTPUT_PATH = BASE_DIR / "dashboard.html"


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, KeyError):
        return None


def load_all_json(directory: Path, pattern: str = "*.json") -> list:
    if not directory.exists():
        return []
    results = []
    for f in sorted(directory.glob(pattern)):
        data = load_json(f)
        if data:
            results.append(data)
    return results


def build_html() -> str:
    """Generate the full interactive dashboard HTML."""
    # Embed current state as fallback data
    book = load_json(BOOK_PATH) or {"nav": 10_000_000, "initial_nav": 10_000_000, "cash_pct": 1.0, "positions": [], "trade_journal": []}
    history = load_json(HISTORY_PATH) or []
    debates = load_all_json(DEBATE_DIR)
    risks = load_all_json(RISK_DIR)
    scores = load_all_json(SCORES_DIR)
    logs = load_all_json(LOGS_DIR, "cycle_*.json")

    now = datetime.now()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agentic Trading Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
</head>
<body>
"""
    html += build_css()
    html += build_sidebar()
    html += build_main_shell()
    html += build_javascript(book, history, debates, risks, scores, logs)
    html += "\n</body>\n</html>"
    return html


def build_css() -> str:
    return """
<style>
:root {
    --bg-primary: #101010;
    --bg-secondary: #161616;
    --bg-card: #1c1c1c;
    --bg-hover: #242424;
    --border: #2e2e2e;
    --text-primary: #e8e8e8;
    --text-secondary: #a0a0a0;
    --text-muted: #6b6b6b;
    --brand-gold: #c8a96e;
    --brand-gold-dim: #8a7040;
    --steel-blue: #5b8ab5;
    --positive: #00c853;
    --negative: #ff1744;
    --warning: #ffab00;
    --sidebar-w: 240px;
    --header-h: 64px;
    --ease: all 0.2s ease;
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg-primary); color: var(--text-primary);
    min-height: 100vh; overflow-x: hidden;
}

/* SIDEBAR */
.sidebar {
    position:fixed; top:0; left:0; width:var(--sidebar-w); height:100vh;
    background:var(--bg-secondary); border-right:1px solid var(--border);
    display:flex; flex-direction:column; z-index:100;
}
.sidebar-brand { padding:20px 24px; border-bottom:1px solid var(--border); }
.sidebar-brand h1 { font-size:1.1em; font-weight:700; color:var(--brand-gold); letter-spacing:-0.02em; }
.sidebar-brand .sub { font-size:0.7em; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-top:2px; }
.sidebar-nav { flex:1; padding:16px 12px; overflow-y:auto; }
.nav-label { font-size:0.68em; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:1.2px; padding:12px 12px 6px; }
.nav-item {
    display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:8px;
    color:var(--text-secondary); font-size:0.88em; font-weight:500; cursor:pointer;
    transition:var(--ease); margin-bottom:2px; border-left:3px solid transparent;
}
.nav-item:hover { background:var(--bg-hover); color:var(--text-primary); }
.nav-item.active { background:var(--bg-card); color:#fff; border-left-color:var(--brand-gold); }
.nav-item .badge-count {
    margin-left:auto; background:var(--negative); color:#fff;
    font-size:0.7em; font-weight:700; padding:2px 7px; border-radius:10px; min-width:18px; text-align:center;
}
.sidebar-footer { padding:16px 20px; border-top:1px solid var(--border); font-size:0.72em; color:var(--text-muted); }

/* MAIN */
.main { margin-left:var(--sidebar-w); min-height:100vh; }
.topbar {
    position:sticky; top:0; height:var(--header-h);
    background:rgba(16,16,16,0.88); backdrop-filter:blur(12px);
    border-bottom:1px solid var(--border);
    display:flex; align-items:center; justify-content:space-between;
    padding:0 32px; z-index:50;
}
.topbar-left h2 { font-size:1.1em; font-weight:600; }
.topbar-right { display:flex; align-items:center; gap:20px; }
.topbar-stat .label { font-size:0.7em; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px; }
.topbar-stat .value { font-size:1.05em; font-weight:700; }
.content { padding:28px 32px; }

/* PANELS */
.panel { display:none; animation:fadeIn 0.3s ease; }
.panel.active { display:block; }
@keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }

/* CARDS & METRICS */
.metrics-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; margin-bottom:28px; }
.metric-card {
    background:var(--bg-card); border:1px solid var(--border); border-radius:12px;
    padding:20px; transition:var(--ease); position:relative; overflow:hidden;
}
.metric-card:hover { border-color:var(--brand-gold); transform:translateY(-2px); box-shadow:0 8px 24px rgba(0,0,0,0.3); }
.metric-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background:linear-gradient(90deg,var(--brand-gold),var(--brand-gold-dim)); opacity:0; transition:var(--ease); }
.metric-card:hover::before { opacity:1; }
.metric-label { font-size:0.75em; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.8px; font-weight:600; }
.metric-value { font-size:1.6em; font-weight:800; margin-top:6px; }
.metric-sub { font-size:0.78em; color:var(--text-secondary); margin-top:4px; }

/* SECTION TITLE */
.section-title {
    font-size:0.78em; font-weight:700; color:var(--brand-gold-dim);
    text-transform:uppercase; letter-spacing:1.2px; margin-bottom:16px;
    display:flex; align-items:center; gap:8px;
}
.section-title::after { content:''; flex:1; height:1px; background:var(--border); }

/* TABLES */
.data-table { width:100%; border-collapse:separate; border-spacing:0; background:var(--bg-card); border:1px solid var(--border); border-radius:12px; overflow:hidden; }
.data-table thead th { background:var(--bg-secondary); color:var(--text-muted); font-size:0.72em; font-weight:700; text-transform:uppercase; letter-spacing:0.8px; padding:14px 16px; text-align:left; border-bottom:1px solid var(--border); }
.data-table tbody td { padding:14px 16px; font-size:0.88em; border-bottom:1px solid var(--border); transition:var(--ease); }
.data-table tbody tr:last-child td { border-bottom:none; }
.data-table tbody tr:hover td { background:var(--bg-hover); }

/* BADGES */
.badge { display:inline-flex; align-items:center; gap:5px; padding:4px 10px; border-radius:20px; font-size:0.78em; font-weight:600; }
.badge-positive { background:rgba(0,200,83,0.12); color:var(--positive); }
.badge-negative { background:rgba(255,23,68,0.12); color:var(--negative); }
.badge-warning { background:rgba(255,171,0,0.12); color:var(--warning); }
.badge-neutral { background:rgba(160,160,160,0.1); color:var(--text-secondary); }
.badge-blue { background:rgba(91,138,181,0.12); color:var(--steel-blue); }

/* P&L */
.positive { color:var(--positive); }
.negative { color:var(--negative); }
.neutral { color:var(--text-muted); }

/* PENDING ORDER CARD */
.pending-card {
    background:var(--bg-card); border:1px solid var(--border); border-radius:14px;
    padding:24px; margin-bottom:16px; position:relative; overflow:hidden;
    transition:var(--ease);
}
.pending-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background:linear-gradient(90deg, var(--brand-gold), var(--steel-blue)); }
.pending-card:hover { border-color:#3a3a3a; }
.pending-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:16px; }
.pending-header h3 { font-size:1.2em; font-weight:800; }
.pending-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:14px; margin-bottom:16px; }
.pending-field .pf-label { font-size:0.7em; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px; }
.pending-field .pf-value { font-size:0.95em; font-weight:600; margin-top:3px; }
.pending-rationale { font-size:0.88em; color:var(--text-secondary); line-height:1.6; padding:14px 0; border-top:1px solid var(--border); }
.pending-actions { display:flex; gap:12px; margin-top:16px; padding-top:16px; border-top:1px solid var(--border); }
.btn {
    padding:10px 24px; border-radius:8px; font-size:0.88em; font-weight:700;
    border:none; cursor:pointer; transition:var(--ease); letter-spacing:0.3px;
}
.btn-accept { background:var(--positive); color:#000; }
.btn-accept:hover { background:#00e05b; transform:translateY(-1px); }
.btn-deny { background:var(--bg-hover); color:var(--text-secondary); border:1px solid var(--border); }
.btn-deny:hover { background:var(--negative); color:#fff; border-color:var(--negative); }
.btn-close { background:var(--bg-hover); color:var(--text-secondary); border:1px solid var(--border); font-size:0.8em; padding:6px 14px; }
.btn-close:hover { background:var(--negative); color:#fff; border-color:var(--negative); }
.btn-mark { background:var(--bg-hover); color:var(--text-secondary); border:1px solid var(--border); font-size:0.8em; padding:6px 14px; }
.btn-mark:hover { background:var(--steel-blue); color:#fff; border-color:var(--steel-blue); }
.btn:disabled { opacity:0.4; cursor:not-allowed; transform:none; }

/* EQUITY CURVE */
.equity-chart { background:var(--bg-card); border:1px solid var(--border); border-radius:12px; padding:20px; margin-bottom:24px; }
.equity-chart svg { width:100%; height:180px; }

/* TIMELINE */
.timeline { position:relative; padding-left:28px; }
.timeline::before { content:''; position:absolute; left:8px; top:0; bottom:0; width:2px; background:var(--border); }
.tl-item { position:relative; padding-bottom:24px; }
.tl-item::before { content:''; position:absolute; left:-24px; top:6px; width:10px; height:10px; border-radius:50%; background:var(--steel-blue); border:2px solid var(--bg-primary); }
.tl-time { font-size:0.72em; color:var(--text-muted); }
.tl-content { margin-top:4px; font-size:0.88em; color:var(--text-secondary); }
.tl-stats { display:flex; gap:16px; margin-top:6px; }
.tl-stat { font-size:0.78em; color:var(--text-muted); }
.tl-stat strong { color:var(--text-primary); }

/* DEBATE */
.debate-entry { background:var(--bg-secondary); border:1px solid var(--border); border-radius:10px; padding:18px; margin-bottom:12px; transition:var(--ease); }
.debate-entry:hover { border-color:#4a7a9e; }
.debate-header { display:flex; align-items:center; gap:10px; margin-bottom:10px; }
.debate-agent { font-size:0.82em; font-weight:700; }
.debate-body { font-size:0.88em; color:var(--text-secondary); line-height:1.6; }

/* RISK FACTORS */
.factor-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:10px; }
.factor-item { background:var(--bg-secondary); border:1px solid var(--border); border-radius:8px; padding:12px; text-align:center; }
.factor-name { font-size:0.7em; color:var(--text-muted); text-transform:uppercase; }
.factor-value { font-size:1.1em; font-weight:700; margin-top:4px; }

/* SIGNALS */
.signal-list { display:flex; flex-wrap:wrap; gap:8px; }
.signal-chip { display:inline-flex; align-items:center; gap:6px; padding:6px 12px; background:var(--bg-secondary); border:1px solid var(--border); border-radius:20px; font-size:0.8em; font-weight:500; }
.signal-dot { width:7px; height:7px; border-radius:50%; }
.signal-dot.strong { background:var(--positive); }
.signal-dot.moderate { background:var(--warning); }
.signal-dot.weak { background:var(--text-muted); }

/* EMPTY */
.empty-state { padding:48px 24px; text-align:center; color:var(--text-muted); }
.empty-icon { font-size:2.2em; margin-bottom:12px; opacity:0.4; }
.empty-text { font-size:0.92em; }

/* TOAST */
.toast { position:fixed; bottom:24px; right:24px; background:var(--bg-card); border:1px solid var(--border); border-radius:10px; padding:14px 20px; font-size:0.88em; z-index:9999; animation:slideUp 0.3s ease; box-shadow:0 8px 32px rgba(0,0,0,0.4); }
.toast.success { border-color:var(--positive); }
.toast.error { border-color:var(--negative); }
@keyframes slideUp { from{transform:translateY(20px);opacity:0} to{transform:translateY(0);opacity:1} }

/* RESPONSIVE */
@media(max-width:768px) { .sidebar{display:none} .main{margin-left:0} .metrics-grid{grid-template-columns:repeat(2,1fr)} }
::-webkit-scrollbar{width:6px} ::-webkit-scrollbar-track{background:var(--bg-primary)} ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
</style>
"""


def build_sidebar() -> str:
    return """
<nav class="sidebar">
    <div class="sidebar-brand">
        <h1>Agentic Trading</h1>
        <div class="sub">Portfolio System</div>
    </div>
    <div class="sidebar-nav">
        <div class="nav-label">Dashboard</div>
        <div class="nav-item active" data-tab="overview" onclick="switchTab('overview')">Overview</div>
        <div class="nav-item" data-tab="pending" onclick="switchTab('pending')">
            Pending Orders <span class="badge-count" id="pending-count" style="display:none;">0</span>
        </div>
        <div class="nav-item" data-tab="positions" onclick="switchTab('positions')">Positions</div>
        <div class="nav-item" data-tab="journal" onclick="switchTab('journal')">Trade Journal</div>

        <div class="nav-label">Analysis</div>
        <div class="nav-item" data-tab="debate" onclick="switchTab('debate')">Agent Debate</div>
        <div class="nav-item" data-tab="risk" onclick="switchTab('risk')">Risk</div>
        <div class="nav-item" data-tab="technical" onclick="switchTab('technical')">Technical</div>

        <div class="nav-label">History</div>
        <div class="nav-item" data-tab="timeline" onclick="switchTab('timeline')">Cycle History</div>
    </div>
    <div class="sidebar-footer">
        <button class="btn btn-mark" onclick="markToMarket()" style="width:100%;margin-bottom:8px;">Refresh Prices</button>
        <div>Auto-refreshes every 30s</div>
    </div>
</nav>
"""


def build_main_shell() -> str:
    return """
<div class="main">
    <header class="topbar">
        <div class="topbar-left"><h2 id="page-title">Portfolio Overview</h2></div>
        <div class="topbar-right">
            <div class="topbar-stat"><div class="label">NAV</div><div class="value" id="topbar-nav" style="color:var(--brand-gold);">—</div></div>
            <div class="topbar-stat"><div class="label">P&L</div><div class="value" id="topbar-pnl">—</div></div>
            <div class="topbar-stat"><div class="label">Cash</div><div class="value" id="topbar-cash">—</div></div>
            <div class="topbar-stat"><div class="label">Positions</div><div class="value" id="topbar-pos">—</div></div>
        </div>
    </header>
    <div class="content">
        <div class="panel active" id="panel-overview"></div>
        <div class="panel" id="panel-pending"></div>
        <div class="panel" id="panel-positions"></div>
        <div class="panel" id="panel-journal"></div>
        <div class="panel" id="panel-debate"></div>
        <div class="panel" id="panel-risk"></div>
        <div class="panel" id="panel-technical"></div>
        <div class="panel" id="panel-timeline"></div>
    </div>
</div>
<div id="toast-container"></div>
"""


def build_javascript(book, history, debates, risks, scores, logs) -> str:
    # Embed fallback data for static file mode
    embedded = json.dumps({
        "book": book,
        "history": history,
        "debates": debates,
        "risks": risks,
        "scores": scores,
        "logs": logs,
    })

    js1 = f"""
<script>
// Embedded fallback data (used when not served via API)
const EMBEDDED = {embedded};

// State
let state = {{
    book: EMBEDDED.book,
    pending: [],
    history: EMBEDDED.history || [],
    debates: EMBEDDED.debates || [],
    risks: EMBEDDED.risks || [],
    scores: EMBEDDED.scores || [],
    logs: EMBEDDED.logs || [],
    apiAvailable: false,
}};

// ─── API ────────────────────────────────────────────────────────────────────
const API = '';  // same origin when served by Flask

async function apiFetch(path) {{
    try {{
        const r = await fetch(API + path);
        if (!r.ok) throw new Error(r.statusText);
        state.apiAvailable = true;
        return await r.json();
    }} catch(e) {{
        return null;
    }}
}}

async function apiPost(path, body) {{
    try {{
        const r = await fetch(API + path, {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: body ? JSON.stringify(body) : undefined,
        }});
        if (!r.ok) {{
            const err = await r.json();
            throw new Error(err.error || r.statusText);
        }}
        return await r.json();
    }} catch(e) {{
        showToast(e.message, 'error');
        return null;
    }}
}}

async function refreshAll() {{
    const [bookData, pendingData, historyData] = await Promise.all([
        apiFetch('/api/book'),
        apiFetch('/api/pending'),
        apiFetch('/api/history'),
    ]);
    if (bookData) state.book = bookData;
    if (pendingData) {{ state.pending = pendingData.pending || []; }}
    if (historyData) state.history = historyData.history || [];

    // Update debates/risk/scores/logs less frequently
    const [debateData, riskData, scoreData, logData] = await Promise.all([
        apiFetch('/api/debates'),
        apiFetch('/api/risk'),
        apiFetch('/api/scores'),
        apiFetch('/api/logs'),
    ]);
    if (debateData) state.debates = debateData.debates || [];
    if (riskData) state.risks = riskData.risks || [];
    if (scoreData) state.scores = scoreData.scores || [];
    if (logData) state.logs = logData.logs || [];

    renderAll();
}}

async function markToMarket() {{
    showToast('Refreshing prices...', 'info');
    const r = await apiFetch('/api/mark');
    if (r) {{
        showToast(`Marked to market — NAV: ${{formatMoney(r.nav)}}`, 'success');
        await refreshAll();
    }}
}}

async function acceptOrder(orderId) {{
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = 'Executing...';
    const r = await apiPost(`/api/accept/${{orderId}}`);
    if (r) {{
        showToast(`Accepted: ${{r.ticker}} @ $${{r.entry_price?.toFixed(2)}}`, 'success');
        await refreshAll();
    }}
    btn.disabled = false;
    btn.textContent = 'Accept';
}}

async function denyOrder(orderId) {{
    const btn = event.target;
    btn.disabled = true;
    const r = await apiPost(`/api/deny/${{orderId}}`);
    if (r) {{
        showToast(`Denied: ${{r.proposal_id}}`, 'success');
        await refreshAll();
    }}
    btn.disabled = false;
    btn.textContent = 'Deny';
}}

async function closePosition(ticker) {{
    if (!confirm(`Close position in ${{ticker}} at market?`)) return;
    const r = await apiPost(`/api/close/${{ticker}}`);
    if (r) {{
        showToast(`Closed ${{ticker}} — P&L: ${{(r.realized_pnl_pct*100).toFixed(2)}}%`, r.realized_pnl_pct >= 0 ? 'success' : 'error');
        await refreshAll();
    }}
}}

// ─── RENDER ─────────────────────────────────────────────────────────────────
function renderAll() {{
    renderTopbar();
    renderOverview();
    renderPending();
    renderPositions();
    renderJournal();
    renderDebate();
    renderRisk();
    renderTechnical();
    renderTimeline();
    updatePendingBadge();
}}

function renderTopbar() {{
    const b = state.book;
    const nav = b.nav || b.initial_nav || 10000000;
    const initial = b.initial_nav || 10000000;
    const pnl = (nav - initial) / initial;
    const activePos = (b.positions || []).filter(p => p.status === 'active').length;

    document.getElementById('topbar-nav').textContent = formatMoney(nav);
    const pnlEl = document.getElementById('topbar-pnl');
    pnlEl.textContent = formatPct(pnl);
    pnlEl.className = 'value ' + pnlClass(pnl);
    document.getElementById('topbar-cash').textContent = (b.cash_pct * 100).toFixed(0) + '%';
    document.getElementById('topbar-pos').textContent = activePos;
}}

function renderOverview() {{
    const b = state.book;
    const nav = b.nav || 10000000;
    const initial = b.initial_nav || 10000000;
    const pnl = (nav - initial) / initial;
    const activePos = (b.positions || []).filter(p => p.status === 'active');
    const grossExp = activePos.reduce((s, p) => s + (p.size_pct_nav || 0), 0) * 2;

    let html = `
        <div class="metrics-grid">
            <div class="metric-card"><div class="metric-label">Net Asset Value</div><div class="metric-value" style="color:var(--brand-gold);">${{formatMoney(nav)}}</div><div class="metric-sub">Initial: ${{formatMoney(initial)}}</div></div>
            <div class="metric-card"><div class="metric-label">Total P&L</div><div class="metric-value ${{pnlClass(pnl)}}">${{formatPct(pnl)}}</div><div class="metric-sub">${{formatMoney(nav - initial)}} since inception</div></div>
            <div class="metric-card"><div class="metric-label">Cash</div><div class="metric-value">${{(b.cash_pct*100).toFixed(1)}}%</div><div class="metric-sub">${{formatMoney(nav * b.cash_pct)}} available</div></div>
            <div class="metric-card"><div class="metric-label">Active Positions</div><div class="metric-value">${{activePos.length}}</div><div class="metric-sub">Gross: ${{(grossExp*100).toFixed(1)}}%</div></div>
        </div>`;

    // Equity curve
    if (state.history.length > 1) {{
        html += `<div class="section-title">Equity Curve</div>`;
        html += renderEquityCurve(state.history);
    }}

    // Quick position summary
    if (activePos.length) {{
        html += `<div class="section-title">Position Summary</div><table class="data-table"><thead><tr><th>Ticker</th><th>Direction</th><th>Hedge</th><th>P&L</th><th>Size</th><th></th></tr></thead><tbody>`;
        for (const p of activePos) {{
            const cpnl = p.combined_pnl_pct;
            html += `<tr><td style="font-weight:600;">${{p.ticker}}</td><td>${{p.direction?.toUpperCase()}}</td><td>${{p.hedge_ticker||'—'}}</td><td class="${{pnlClass(cpnl)}}" style="font-weight:700;">${{formatPct(cpnl)}}</td><td>${{(p.size_pct_nav*100).toFixed(1)}}%</td><td><button class="btn btn-close" onclick="closePosition('${{p.ticker}}')">Close</button></td></tr>`;
        }}
        html += `</tbody></table>`;
    }}

    // Pending orders teaser
    if (state.pending.length) {{
        html += `<div class="section-title" style="margin-top:28px;">${{state.pending.length}} Pending Order${{state.pending.length>1?'s':''}}</div>`;
        html += `<p style="color:var(--text-secondary);font-size:0.9em;cursor:pointer;" onclick="switchTab('pending')">You have trade recommendations awaiting your decision. <span style="color:var(--brand-gold);font-weight:600;">Review &rarr;</span></p>`;
    }}

    document.getElementById('panel-overview').innerHTML = html;
}}
</script>
"""

    # Continue JavaScript in another script block
    js2 = f"""
<script>
function renderPending() {{
    const panel = document.getElementById('panel-pending');
    if (!state.pending.length) {{
        panel.innerHTML = '<div class="empty-state"><div class="empty-icon">&#10003;</div><div class="empty-text">No pending orders. All recommendations have been processed.</div></div>';
        return;
    }}

    let html = '<div class="section-title">Pending Trade Recommendations</div>';
    for (const o of state.pending) {{
        const prop = o._proposal || {{}};
        const tech = o._tech_score || {{}};
        const risk = o._risk || {{}};
        const id = o.order_id || o.proposal_id;

        html += `
        <div class="pending-card">
            <div class="pending-header">
                <h3>${{o.ticker}} — ${{(o.direction||'').toUpperCase()}}</h3>
                <span class="badge badge-warning">AWAITING DECISION</span>
            </div>
            <div class="pending-grid">
                <div class="pending-field"><div class="pf-label">Hedge</div><div class="pf-value">${{o.hedge_ticker||'—'}} (${{o.hedge_direction||'short'}})</div></div>
                <div class="pending-field"><div class="pf-label">Size</div><div class="pf-value">${{(o.size_pct_nav*100).toFixed(1)}}% NAV</div></div>
                <div class="pending-field"><div class="pf-label">Conviction</div><div class="pf-value">${{o.conviction||'—'}}/10</div></div>
                <div class="pending-field"><div class="pf-label">Technical</div><div class="pf-value">${{tech.technical_score||'—'}}/10</div></div>
                <div class="pending-field"><div class="pf-label">Risk</div><div class="pf-value"><span class="badge ${{risk.decision==='approved'?'badge-positive':'badge-negative'}}">${{(risk.decision||'—').toUpperCase()}}</span></div></div>
                <div class="pending-field"><div class="pf-label">Stop</div><div class="pf-value" style="font-size:0.85em;">${{o.stop_loss_method||'—'}}</div></div>
                <div class="pending-field"><div class="pf-label">Take Profit</div><div class="pf-value" style="font-size:0.85em;">${{o.take_profit||'—'}}</div></div>
                <div class="pending-field"><div class="pf-label">Holding</div><div class="pf-value">${{o.expected_holding_period||'—'}}</div></div>
            </div>
            <div class="pending-rationale">
                <strong>PM Rationale:</strong> ${{escapeHtml(o.pm_rationale||'No rationale provided.')}}
            </div>
            ${{prop.thesis_summary ? `<div style="font-size:0.85em;color:var(--text-muted);margin-top:8px;line-height:1.5;"><strong>Thesis:</strong> ${{escapeHtml(prop.thesis_summary)}}</div>` : ''}}
            ${{prop.variant_perception ? `<div style="font-size:0.85em;color:var(--text-muted);margin-top:6px;line-height:1.5;"><strong>Variant:</strong> ${{escapeHtml(prop.variant_perception)}}</div>` : ''}}
            <div class="pending-actions">
                <button class="btn btn-accept" onclick="acceptOrder('${{id}}')">Accept &amp; Execute</button>
                <button class="btn btn-deny" onclick="denyOrder('${{id}}')">Deny</button>
            </div>
        </div>`;
    }}
    panel.innerHTML = html;
}}

function renderPositions() {{
    const panel = document.getElementById('panel-positions');
    const positions = (state.book.positions || []).filter(p => p.status === 'active');
    const closed = (state.book.positions || []).filter(p => p.status === 'closed');

    if (!positions.length && !closed.length) {{
        panel.innerHTML = '<div class="empty-state"><div class="empty-icon">&#9898;</div><div class="empty-text">No positions. Accept a pending order to open your first trade.</div></div>';
        return;
    }}

    let html = '';
    if (positions.length) {{
        html += '<div class="section-title">Active Positions</div><table class="data-table"><thead><tr><th>Ticker</th><th>Dir</th><th>Hedge</th><th>Entry</th><th>Current</th><th>P&L</th><th>Size</th><th>Conv.</th><th>Stop</th><th>Days</th><th></th></tr></thead><tbody>';
        for (const p of positions) {{
            const cpnl = p.combined_pnl_pct;
            const entryDate = p.entry_date ? new Date(p.entry_date) : null;
            const days = entryDate ? Math.floor((Date.now() - entryDate.getTime()) / 86400000) : '—';
            html += `<tr>
                <td style="font-weight:700;">${{p.ticker}}</td>
                <td><span class="badge badge-${{p.direction==='long'?'positive':'negative'}}">${{(p.direction||'').toUpperCase()}}</span></td>
                <td>${{p.hedge_ticker||'—'}} <span style="color:var(--text-muted);">(${{p.hedge_direction||'short'}})</span></td>
                <td>$${{p.entry_price?.toFixed(2)||'—'}}</td>
                <td>$${{p.current_price?.toFixed(2)||'—'}}</td>
                <td class="${{pnlClass(cpnl)}}" style="font-weight:700;">${{formatPct(cpnl)}}</td>
                <td>${{(p.size_pct_nav*100).toFixed(1)}}%</td>
                <td>${{p.conviction||'—'}}/10</td>
                <td style="font-size:0.8em;color:var(--text-muted);">${{p.stop_loss_method||'—'}}</td>
                <td>${{days}}</td>
                <td><button class="btn btn-close" onclick="closePosition('${{p.ticker}}')">Close</button></td>
            </tr>`;
        }}
        html += '</tbody></table>';
    }}

    if (closed.length) {{
        html += '<div class="section-title" style="margin-top:28px;">Closed Positions</div><table class="data-table"><thead><tr><th>Ticker</th><th>Dir</th><th>Entry</th><th>Exit</th><th>Realized P&L</th><th>Exit Date</th></tr></thead><tbody>';
        for (const p of closed) {{
            const rpnl = p.realized_pnl_pct;
            html += `<tr>
                <td style="font-weight:600;">${{p.ticker}}</td>
                <td>${{(p.direction||'').toUpperCase()}}</td>
                <td>$${{p.entry_price?.toFixed(2)||'—'}}</td>
                <td>$${{p.exit_price?.toFixed(2)||'—'}}</td>
                <td class="${{pnlClass(rpnl)}}" style="font-weight:700;">${{formatPct(rpnl)}}</td>
                <td style="color:var(--text-muted);">${{p.exit_date||'—'}}</td>
            </tr>`;
        }}
        html += '</tbody></table>';
    }}

    panel.innerHTML = html;
}}

function renderJournal() {{
    const panel = document.getElementById('panel-journal');
    const journal = state.book.trade_journal || [];
    if (!journal.length) {{
        panel.innerHTML = '<div class="empty-state"><div class="empty-icon">&#128214;</div><div class="empty-text">No trade history yet.</div></div>';
        return;
    }}
    let html = '<div class="section-title">Trade Journal</div><table class="data-table"><thead><tr><th>Action</th><th>Ticker</th><th>Direction</th><th>Hedge</th><th>Entry</th><th>P&L</th><th>Timestamp</th></tr></thead><tbody>';
    for (const e of [...journal].reverse()) {{
        const o = e.order || {{}};
        const ticker = o.ticker || e.ticker || '—';
        const dir = o.direction || e.direction || '';
        const hedge = o.hedge_ticker || e.hedge || '—';
        const ep = e.entry_price || o.entry_price;
        const pnl = e.realized_pnl_pct;
        const actionClass = e.action === 'open' ? 'badge-positive' : e.action === 'close' ? 'badge-negative' : 'badge-neutral';
        html += `<tr>
            <td><span class="badge ${{actionClass}}">${{(e.action||'').toUpperCase()}}</span></td>
            <td style="font-weight:600;">${{ticker}}</td>
            <td>${{dir.toUpperCase()}}</td>
            <td>${{hedge}}</td>
            <td>${{ep ? '$'+Number(ep).toFixed(2) : '—'}}</td>
            <td class="${{pnlClass(pnl)}}">${{pnl != null ? formatPct(pnl) : '—'}}</td>
            <td style="font-size:0.82em;color:var(--text-muted);">${{e.timestamp||'—'}}</td>
        </tr>`;
    }}
    html += '</tbody></table>';
    panel.innerHTML = html;
}}

function renderDebate() {{
    const panel = document.getElementById('panel-debate');
    if (!state.debates.length) {{
        panel.innerHTML = '<div class="empty-state"><div class="empty-icon">&#128172;</div><div class="empty-text">No debate records yet.</div></div>';
        return;
    }}
    let html = '<div class="section-title">Agent Debate History</div>';
    for (const d of [...state.debates].reverse()) {{
        const stanceClass = d.stance==='support' ? 'badge-blue' : d.stance==='challenge' ? 'badge-negative' : 'badge-neutral';
        html += `<div class="debate-entry">
            <div class="debate-header">
                <span class="debate-agent">${{(d.agent_id||'').replace(/_/g,' ').replace(/\\b\\w/g,c=>c.toUpperCase())}}</span>
                <span class="badge ${{stanceClass}}">${{(d.stance||'').toUpperCase()}}</span>
                <span style="font-size:0.75em;color:var(--text-muted);margin-left:auto;">Round ${{d.round||''}}</span>
                ${{d.revised_conviction ? `<span style="margin-left:12px;font-size:0.8em;color:var(--text-muted);">Conv: <strong>${{d.revised_conviction}}/10</strong></span>` : ''}}
            </div>
            <div class="debate-body">${{escapeHtml(d.argument||'')}}</div>
            <div style="margin-top:6px;font-size:0.72em;color:var(--text-muted);">Re: ${{d.proposal_id||''}}</div>
        </div>`;
    }}
    panel.innerHTML = html;
}}
</script>
"""

    # Third script block: risk, technical, timeline, helpers, init
    js3 = f"""
<script>
function renderRisk() {{
    const panel = document.getElementById('panel-risk');
    if (!state.risks.length) {{
        panel.innerHTML = '<div class="empty-state"><div class="empty-icon">&#9888;</div><div class="empty-text">No risk assessments yet.</div></div>';
        return;
    }}
    const latest = state.risks[state.risks.length - 1];
    const betas = latest.projected_factor_betas || {{}};
    const decClass = latest.decision === 'approved' ? 'badge-positive' : 'badge-negative';

    let factorHtml = '';
    for (const [k, v] of Object.entries(betas)) {{
        const cls = v > 0.03 ? 'positive' : v < -0.03 ? 'negative' : 'neutral';
        factorHtml += `<div class="factor-item"><div class="factor-name">${{k}}</div><div class="factor-value ${{cls}}">${{v > 0 ? '+' : ''}}${{v.toFixed(3)}}</div></div>`;
    }}

    let warningsHtml = '';
    for (const w of (latest.risk_warnings || [])) {{
        warningsHtml += `<li style="padding:4px 0;color:var(--warning);font-size:0.88em;">${{escapeHtml(w)}}</li>`;
    }}

    let html = `
        <div class="section-title">Latest Risk Assessment</div>
        <div class="pending-card" style="margin-bottom:24px;">
            <div class="pending-header"><h3>${{latest.proposal_id||'—'}}</h3><span class="badge ${{decClass}}">${{(latest.decision||'').toUpperCase()}}</span></div>
            <p style="font-size:0.9em;color:var(--text-secondary);line-height:1.6;margin-bottom:16px;">${{escapeHtml(latest.rationale||'')}}</p>
            <div class="metrics-grid">
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Size OK</div><div class="metric-value ${{latest.position_size_ok?'positive':'negative'}}" style="font-size:1.2em;">${{latest.position_size_ok?'&#10003;':'&#10007;'}}</div></div>
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Hedge Valid</div><div class="metric-value ${{latest.hedge_present_and_valid?'positive':'negative'}}" style="font-size:1.2em;">${{latest.hedge_present_and_valid?'&#10003;':'&#10007;'}}</div></div>
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Gross Leverage</div><div class="metric-value" style="font-size:1.2em;">${{((latest.projected_gross_leverage||0)*100).toFixed(1)}}%</div></div>
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Max Size</div><div class="metric-value" style="font-size:1.2em;">${{((latest.max_allowed_size_pct||0)*100).toFixed(1)}}%</div></div>
            </div>
        </div>
        <div class="section-title">Factor Betas</div>
        <div class="factor-grid" style="margin-bottom:24px;">${{factorHtml}}</div>
        ${{warningsHtml ? `<div class="section-title">Risk Warnings</div><ul style="list-style:none;margin-bottom:24px;">${{warningsHtml}}</ul>` : ''}}
    `;
    panel.innerHTML = html;
}}

function renderTechnical() {{
    const panel = document.getElementById('panel-technical');
    if (!state.scores.length) {{
        panel.innerHTML = '<div class="empty-state"><div class="empty-icon">&#128200;</div><div class="empty-text">No technical scores yet.</div></div>';
        return;
    }}
    const latest = state.scores[state.scores.length - 1];
    const score = latest.technical_score || 0;
    const scorePct = score * 10;

    let signalsHtml = '';
    for (const s of (latest.active_signals || [])) {{
        const name = (s.signal||'').replace(/_/g,' ').replace(/\\b\\w/g,c=>c.toUpperCase());
        const val = s.value ? ` (${{s.value}})` : '';
        signalsHtml += `<div class="signal-chip"><span class="signal-dot ${{s.strength||'moderate'}}"></span>${{name}}${{val}}</div>`;
    }}

    const supports = latest.support_levels || [];
    const resistances = latest.resistance_levels || [];
    let levelsHtml = '';
    for (const r of resistances) levelsHtml += `<div class="factor-item" style="border-color:rgba(255,23,68,0.3);"><div class="factor-name">Resistance</div><div class="factor-value negative">$${{r.toFixed(2)}}</div></div>`;
    for (const s of supports) levelsHtml += `<div class="factor-item" style="border-color:rgba(0,200,83,0.3);"><div class="factor-name">Support</div><div class="factor-value positive">$${{s.toFixed(2)}}</div></div>`;

    let html = `
        <div class="section-title">Technical Score</div>
        <div class="pending-card" style="margin-bottom:24px;">
            <div class="pending-header"><h3>${{latest.proposal_id||'—'}}</h3><span class="badge ${{score>=7?'badge-positive':score>=5?'badge-warning':'badge-negative'}}">Score: ${{score}}/10</span></div>
            <div style="margin:16px 0;">
                <div style="display:flex;justify-content:space-between;font-size:0.78em;color:var(--text-muted);margin-bottom:4px;"><span>Bearish</span><span>Neutral</span><span>Bullish</span></div>
                <div style="width:100%;height:12px;background:var(--bg-secondary);border-radius:6px;overflow:hidden;">
                    <div style="width:${{scorePct}}%;height:100%;background:linear-gradient(90deg,var(--negative),var(--warning),var(--positive));border-radius:6px;transition:width 0.8s ease;"></div>
                </div>
            </div>
            <div class="metrics-grid">
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Trend</div><div class="metric-value" style="font-size:1em;text-transform:capitalize;">${{latest.trend_alignment||'—'}}</div></div>
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Momentum</div><div class="metric-value" style="font-size:1em;text-transform:capitalize;">${{(latest.momentum_regime||'—').replace(/_/g,' ')}}</div></div>
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Timing</div><div class="metric-value" style="font-size:1em;text-transform:capitalize;">${{latest.timing_recommendation||'—'}}</div></div>
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Volume</div><div class="metric-value ${{latest.volume_confirmation?'positive':'negative'}}" style="font-size:1em;">${{latest.volume_confirmation?'Confirmed':'No'}}</div></div>
            </div>
            <div style="margin-top:12px;font-size:0.88em;color:var(--text-secondary);line-height:1.6;"><strong>Rationale:</strong> ${{escapeHtml(latest.timing_rationale||'—')}}</div>
        </div>
        <div class="section-title">Active Signals</div>
        <div class="signal-list" style="margin-bottom:24px;">${{signalsHtml || '<span style="color:var(--text-muted);font-size:0.88em;">No signals.</span>'}}</div>
        <div class="section-title">Key Levels</div>
        <div class="factor-grid" style="margin-bottom:24px;">${{levelsHtml}}</div>
        <div class="metrics-grid">
            <div class="metric-card" style="padding:14px;"><div class="metric-label">Entry</div><div class="metric-value" style="font-size:1.1em;">$${{(latest.suggested_entry||0).toFixed(2)}}</div></div>
            <div class="metric-card" style="padding:14px;"><div class="metric-label">Stop</div><div class="metric-value negative" style="font-size:1.1em;">$${{(latest.suggested_stop_loss||0).toFixed(2)}}</div></div>
            <div class="metric-card" style="padding:14px;"><div class="metric-label">Target</div><div class="metric-value positive" style="font-size:1.1em;">$${{(latest.suggested_take_profit||0).toFixed(2)}}</div></div>
        </div>
    `;
    panel.innerHTML = html;
}}

function renderTimeline() {{
    const panel = document.getElementById('panel-timeline');
    if (!state.logs.length) {{
        panel.innerHTML = '<div class="empty-state"><div class="empty-icon">&#9200;</div><div class="empty-text">No cycle logs yet.</div></div>';
        return;
    }}
    let html = '<div class="section-title">Cycle History</div><div class="timeline">';
    for (const log of [...state.logs].reverse()) {{
        let ts = log.timestamp || '';
        try {{ ts = new Date(ts).toLocaleString('en-US', {{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}}); }} catch(e) {{}}
        html += `<div class="tl-item">
            <div class="tl-time">${{ts}}</div>
            <div class="tl-content">Cycle completed</div>
            <div class="tl-stats">
                <div class="tl-stat">Proposals: <strong>${{log.proposals_generated||0}}</strong></div>
                <div class="tl-stat">Orders: <strong>${{log.orders_executed||0}}</strong></div>
                <div class="tl-stat">Positions: <strong>${{log.book_positions||0}}</strong></div>
                <div class="tl-stat">NAV: <strong>${{formatMoney(log.nav)}}</strong></div>
            </div>
        </div>`;
    }}
    html += '</div>';
    panel.innerHTML = html;
}}

// ─── EQUITY CURVE (SVG) ─────────────────────────────────────────────────────
function renderEquityCurve(history) {{
    if (!history.length) return '';
    const W = 800, H = 160, PAD = 40;
    const navs = history.map(h => h.nav || 10000000);
    const minNav = Math.min(...navs) * 0.999;
    const maxNav = Math.max(...navs) * 1.001;
    const rangeNav = maxNav - minNav || 1;

    const scaleX = (i) => PAD + (i / (navs.length - 1 || 1)) * (W - PAD * 2);
    const scaleY = (v) => H - PAD - ((v - minNav) / rangeNav) * (H - PAD * 2);

    let pathD = `M ${{scaleX(0)}} ${{scaleY(navs[0])}}`;
    for (let i = 1; i < navs.length; i++) {{
        pathD += ` L ${{scaleX(i)}} ${{scaleY(navs[i])}}`;
    }}

    // Fill area
    const areaD = pathD + ` L ${{scaleX(navs.length-1)}} ${{H-PAD}} L ${{scaleX(0)}} ${{H-PAD}} Z`;

    // Color: green if up, red if down
    const isUp = navs[navs.length-1] >= navs[0];
    const lineColor = isUp ? 'var(--positive)' : 'var(--negative)';
    const fillColor = isUp ? 'rgba(0,200,83,0.08)' : 'rgba(255,23,68,0.08)';

    return `<div class="equity-chart">
        <svg viewBox="0 0 ${{W}} ${{H}}" preserveAspectRatio="none">
            <path d="${{areaD}}" fill="${{fillColor}}" />
            <path d="${{pathD}}" fill="none" stroke="${{lineColor}}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            <line x1="${{PAD}}" y1="${{H-PAD}}" x2="${{W-PAD}}" y2="${{H-PAD}}" stroke="var(--border)" stroke-width="1" />
            <text x="${{PAD}}" y="${{H-PAD+14}}" fill="var(--text-muted)" font-size="10">${{history[0].date||''}}</text>
            <text x="${{W-PAD}}" y="${{H-PAD+14}}" fill="var(--text-muted)" font-size="10" text-anchor="end">${{history[history.length-1].date||''}}</text>
            <text x="${{PAD-4}}" y="${{scaleY(maxNav)+4}}" fill="var(--text-muted)" font-size="10" text-anchor="end">${{formatMoney(maxNav)}}</text>
            <text x="${{PAD-4}}" y="${{scaleY(minNav)+4}}" fill="var(--text-muted)" font-size="10" text-anchor="end">${{formatMoney(minNav)}}</text>
        </svg>
    </div>`;
}}

// ─── HELPERS ────────────────────────────────────────────────────────────────
function formatMoney(v) {{ if (v == null) return '—'; return '$' + Math.round(v).toLocaleString(); }}
function formatPct(v) {{ if (v == null) return '—'; return (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%'; }}
function pnlClass(v) {{ if (v == null) return 'neutral'; return v > 0 ? 'positive' : v < 0 ? 'negative' : 'neutral'; }}
function escapeHtml(s) {{ if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }}

function updatePendingBadge() {{
    const el = document.getElementById('pending-count');
    if (state.pending.length > 0) {{
        el.style.display = 'inline';
        el.textContent = state.pending.length;
    }} else {{
        el.style.display = 'none';
    }}
}}

function showToast(msg, type) {{
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast ' + (type || '');
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}}

const TITLES = {{
    overview: 'Portfolio Overview',
    pending: 'Pending Orders',
    positions: 'Active Positions',
    journal: 'Trade Journal',
    debate: 'Agent Debate',
    risk: 'Risk Assessment',
    technical: 'Technical Analysis',
    timeline: 'Cycle History',
}};

function switchTab(tab) {{
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.getElementById('panel-' + tab).classList.add('active');
    document.querySelector(`[data-tab="${{tab}}"]`).classList.add('active');
    document.getElementById('page-title').textContent = TITLES[tab] || 'Dashboard';
}}

// ─── INIT ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {{
    renderAll();
    await refreshAll();
    // Auto-refresh every 30s
    setInterval(refreshAll, 30000);
}});
</script>
"""

    return js1 + js2 + js3


def main():
    parser = argparse.ArgumentParser(description="Generate portfolio dashboard HTML (v3 interactive)")
    parser.add_argument("--no-open", action="store_true", help="Skip opening browser")
    args = parser.parse_args()

    html = build_html()

    with open(OUTPUT_PATH, "w") as f:
        f.write(html)

    print(f"Dashboard written to: {OUTPUT_PATH}")
    print(f"  Size: {len(html):,} bytes")
    print(f"\n  To use interactively, run:  python3 serve.py")
    print(f"  Then open:  http://127.0.0.1:5100/")

    if not args.no_open:
        subprocess.run(["open", str(OUTPUT_PATH)])


if __name__ == "__main__":
    main()
