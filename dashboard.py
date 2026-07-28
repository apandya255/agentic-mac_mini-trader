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

sys.path.insert(0, str(Path(__file__).parent / "src"))
from data_platform.prices import PriceService

BASE_DIR = Path(__file__).parent
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
    --info-blue: #5b8ab5;
    --positive: #00c853;
    --negative: #ff1744;
    --warning: #ffab00;
    --sidebar-w: 220px;
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
.kpi-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:16px; margin-bottom:28px; }
.metric-card {
    background:var(--bg-card); border:1px solid var(--border); border-radius:12px;
    padding:20px; transition:var(--ease); position:relative; overflow:hidden;
}
.metric-card:hover { border-color:var(--brand-gold); transform:translateY(-2px); box-shadow:0 8px 24px rgba(0,0,0,0.3); }
.metric-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background:linear-gradient(90deg,var(--brand-gold),var(--brand-gold-dim)); opacity:0; transition:var(--ease); }
.metric-card:hover::before { opacity:1; }
.metric-card.clickable { cursor:pointer; }
.metric-card.clickable:hover { border-color:var(--warning); box-shadow:0 8px 24px rgba(255,171,0,0.15); }
.metric-label { font-size:0.75em; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.8px; font-weight:600; }
.metric-value { font-size:1.6em; font-weight:800; margin-top:6px; }
.metric-sub { font-size:0.78em; color:var(--text-secondary); margin-top:4px; }
.trend-indicator { font-size:0.6em; vertical-align:middle; margin-left:4px; }

/* KPI SKELETON / LOADING */
.skeleton-pulse {
    background: linear-gradient(90deg, var(--bg-hover) 25%, var(--border) 50%, var(--bg-hover) 75%);
    background-size: 200% 100%;
    animation: pulse 1.5s infinite;
    border-radius: 6px;
    height: 1.6em;
    width: 80%;
    margin-top: 6px;
}
@keyframes pulse { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

/* KPI GRID RESPONSIVE */
@media(max-width:1024px) {
    .kpi-grid { grid-template-columns:repeat(3,1fr); }
}
@media(max-width:768px) {
    .kpi-grid { grid-template-columns:repeat(2,1fr); gap:10px; }
}

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

/* POSITION TABLE — SORTABLE HEADERS & FILTER */
.position-table-wrapper { overflow-x:auto; -webkit-overflow-scrolling:touch; border-radius:12px; }
.position-filter-input {
    background:var(--bg-card); border:1px solid var(--border); border-radius:8px;
    padding:9px 14px; font-size:0.88em; color:var(--text-primary); width:220px;
    outline:none; transition:var(--ease); font-family:inherit; margin-bottom:14px;
}
.position-filter-input:focus { border-color:var(--brand-gold); }
.position-filter-input::placeholder { color:var(--text-muted); }
.sortable-header {
    cursor:pointer; user-select:none; white-space:nowrap; position:relative;
    transition:var(--ease);
}
.sortable-header:hover { color:var(--brand-gold); }
.sortable-header .sort-arrow { display:inline-block; margin-left:4px; font-size:0.7em; opacity:0.5; transition:var(--ease); }
.sortable-header.sort-asc .sort-arrow { opacity:1; color:var(--brand-gold); }
.sortable-header.sort-desc .sort-arrow { opacity:1; color:var(--brand-gold); transform:rotate(180deg); }
.position-table thead th { position:sticky; top:0; z-index:10; }
.position-table { width:100%; border-collapse:separate; border-spacing:0; background:var(--bg-card); border:1px solid var(--border); border-radius:12px; overflow:hidden; }
.position-table thead th { background:var(--bg-secondary); color:var(--text-muted); font-size:0.72em; font-weight:700; text-transform:uppercase; letter-spacing:0.8px; padding:12px 14px; text-align:left; border-bottom:1px solid var(--border); }
.position-table thead th.num-col { text-align:right; }
.position-table tbody td { padding:12px 14px; font-size:0.88em; border-bottom:1px solid var(--border); transition:var(--ease); vertical-align:middle; }
.position-table tbody td.num-col { text-align:right; font-variant-numeric:tabular-nums; }
.position-table tbody tr:last-child td { border-bottom:none; }
.position-table tbody tr.position-row { cursor:pointer; }
.position-table tbody tr.position-row:hover td { background:var(--bg-hover); }
.position-table tbody tr.position-detail-row td { background:var(--bg-primary); padding:0; border-bottom:1px solid var(--border); }
.position-detail-panel {
    padding:18px 20px; font-size:0.88em; color:var(--text-secondary); line-height:1.6;
    animation:fadeIn 0.2s ease;
}
.position-detail-panel .pdp-section { margin-bottom:10px; }
.position-detail-panel .pdp-section:last-child { margin-bottom:0; }
.position-detail-panel .pdp-label { font-weight:700; color:var(--text-primary); font-size:0.85em; text-transform:uppercase; letter-spacing:0.4px; margin-bottom:3px; }
.position-detail-panel .pdp-value { color:var(--text-secondary); }
.position-detail-panel .pdp-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; }

/* Direction & Status Badges (position table) */
.dir-badge { display:inline-flex; align-items:center; padding:3px 10px; border-radius:14px; font-size:0.75em; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; }
.dir-badge.long { background:rgba(0,200,83,0.12); color:var(--positive); }
.dir-badge.short { background:rgba(255,23,68,0.12); color:var(--negative); }
.status-badge { display:inline-flex; align-items:center; padding:3px 10px; border-radius:14px; font-size:0.72em; font-weight:700; text-transform:uppercase; letter-spacing:0.4px; }
.status-badge.active { background:rgba(0,200,83,0.12); color:var(--positive); }
.status-badge.closed { background:rgba(160,160,160,0.1); color:var(--text-secondary); }
.status-badge.stopped { background:rgba(255,23,68,0.12); color:var(--negative); }

/* Position table skeleton */
.position-skeleton-row td { padding:14px !important; }
.position-skeleton-cell { height:1em; border-radius:4px; background:linear-gradient(90deg, var(--bg-hover) 25%, var(--border) 50%, var(--bg-hover) 75%); background-size:200% 100%; animation:pulse 1.5s infinite; }

/* Review Position Button */
.btn-review { background:var(--bg-hover); color:var(--brand-gold); border:1px solid var(--brand-gold-dim); font-size:0.78em; padding:6px 14px; border-radius:7px; cursor:pointer; font-weight:600; transition:var(--ease); white-space:nowrap; }
.btn-review:hover { background:rgba(200,169,110,0.1); border-color:var(--brand-gold); color:var(--text-primary); }

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

/* EQUITY CHART */
.equity-chart { background:var(--bg-card); border:1px solid var(--border); border-radius:12px; padding:20px; margin-bottom:24px; }
.equity-chart svg { width:100%; height:180px; }
.chart-range-bar { display:flex; align-items:center; gap:6px; margin-bottom:14px; flex-wrap:wrap; }
.chart-range-btn {
    padding:5px 12px; border-radius:6px; font-size:0.75em; font-weight:600;
    border:1px solid var(--border); background:var(--bg-hover); color:var(--text-secondary);
    cursor:pointer; transition:var(--ease); letter-spacing:0.3px;
}
.chart-range-btn:hover { border-color:var(--brand-gold); color:var(--text-primary); }
.chart-range-btn.active { background:var(--brand-gold); color:#000; border-color:var(--brand-gold); }
.chart-drawdown-toggle {
    margin-left:auto; display:flex; align-items:center; gap:6px;
    font-size:0.75em; color:var(--text-muted); cursor:pointer; user-select:none;
}
.chart-drawdown-toggle input[type="checkbox"] { accent-color:var(--brand-gold); cursor:pointer; }
.chart-skeleton {
    background: linear-gradient(90deg, var(--bg-hover) 25%, var(--border) 50%, var(--bg-hover) 75%);
    background-size: 200% 100%;
    animation: pulse 1.5s infinite;
    border-radius: 8px;
    height: 180px;
    width: 100%;
}
.chart-empty-state { text-align:center; padding:40px 20px; color:var(--text-muted); }
.chart-empty-state .ces-icon { font-size:1.8em; margin-bottom:8px; opacity:0.4; }
.chart-empty-state .ces-text { font-size:0.88em; }
.chart-error-state { text-align:center; padding:40px 20px; color:var(--negative); }
.chart-error-state .cer-icon { font-size:1.8em; margin-bottom:8px; opacity:0.6; }
.chart-error-state .cer-text { font-size:0.88em; }
.drawdown-chart { margin-top:12px; }
.drawdown-chart svg { width:100%; height:100px; }

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

/* CHAT */
.chat-container { display:flex; flex-direction:column; height:calc(100vh - var(--header-h) - 80px); max-height:700px; }
.chat-messages { flex:1; overflow-y:auto; padding:16px 0; display:flex; flex-direction:column; gap:12px; }
.chat-msg { max-width:85%; padding:12px 16px; border-radius:12px; font-size:0.9em; line-height:1.6; animation:fadeIn 0.2s ease; }
.chat-msg.user { align-self:flex-end; background:var(--bg-hover); border:1px solid var(--border); color:var(--text-primary); }
.chat-msg.assistant { align-self:flex-start; background:var(--bg-card); border:1px solid var(--border); color:var(--text-secondary); }
.chat-msg.assistant pre { background:var(--bg-primary); padding:8px 12px; border-radius:6px; overflow-x:auto; font-size:0.85em; margin:8px 0; }
.chat-msg.assistant code { font-family:'SF Mono',monospace; font-size:0.88em; }
.chat-input-row { display:flex; gap:10px; padding-top:16px; border-top:1px solid var(--border); }
.chat-input { flex:1; background:var(--bg-card); border:1px solid var(--border); border-radius:10px; padding:12px 16px; color:var(--text-primary); font-size:0.9em; font-family:inherit; resize:none; outline:none; transition:var(--ease); }
.chat-input:focus { border-color:var(--brand-gold); }
.chat-input::placeholder { color:var(--text-muted); }
.chat-send { background:var(--brand-gold); color:#000; border:none; border-radius:10px; padding:12px 20px; font-size:0.88em; font-weight:700; cursor:pointer; transition:var(--ease); white-space:nowrap; }
.chat-send:hover { opacity:0.85; transform:translateY(-1px); }
.chat-send:disabled { opacity:0.4; cursor:not-allowed; transform:none; }
.chat-typing { color:var(--text-muted); font-size:0.82em; font-style:italic; padding:8px 0; }
@keyframes slideUp { from{transform:translateY(20px);opacity:0} to{transform:translateY(0);opacity:1} }

/* RESPONSIVE */
@media(max-width:768px) {
    :root { --sidebar-w:0px; --header-h:56px; }
    .sidebar { display:none; }
    .main { margin-left:0; padding-bottom:72px; }
    .topbar { padding:0 16px; }
    .topbar-left h2 { font-size:0.95em; }
    .topbar-right { gap:12px; }
    .topbar-stat .label { font-size:0.6em; }
    .topbar-stat .value { font-size:0.88em; }
    .dashboard-header { padding:16px; }
    .dashboard-header-top { flex-direction:column; align-items:flex-start; }
    .dashboard-header-title h2 { font-size:1.1em; }
    .header-actions { flex-direction:column; align-items:stretch; width:100%; }
    .btn-header { justify-content:center; }
    .content { padding:16px; }
    .metrics-grid { grid-template-columns:repeat(2,1fr); gap:10px; }
    .metric-card { padding:14px; }
    .metric-value { font-size:1.3em; }
    .metric-label { font-size:0.68em; }
    .section-title { font-size:0.72em; }
    .data-table { display:block; overflow-x:auto; -webkit-overflow-scrolling:touch; }
    .data-table thead, .data-table tbody, .data-table tr { min-width:600px; }
    .data-table thead th { padding:10px 12px; font-size:0.68em; white-space:nowrap; }
    .data-table tbody td { padding:10px 12px; font-size:0.82em; white-space:nowrap; }
    .pending-card { padding:16px; }
    .pending-grid { grid-template-columns:repeat(2,1fr); gap:10px; }
    .pending-header h3 { font-size:1.05em; }
    .pending-actions { flex-direction:column; }
    .pending-actions .btn { width:100%; text-align:center; }
    .btn { padding:12px 20px; font-size:0.9em; }
    .factor-grid { grid-template-columns:repeat(3,1fr); gap:8px; }
    .factor-item { padding:10px 6px; }
    .factor-name { font-size:0.62em; }
    .factor-value { font-size:0.95em; }
    .signal-list { gap:6px; }
    .signal-chip { font-size:0.74em; padding:5px 10px; }
    .debate-entry { padding:14px; }
    .debate-header { flex-wrap:wrap; gap:6px; }
    .debate-body { font-size:0.84em; }
    .equity-chart svg { height:140px; }
    .timeline { padding-left:22px; }
    .tl-stats { flex-wrap:wrap; gap:8px; }
    .rec-grid { grid-template-columns:repeat(2,1fr); }
    .empty-state { padding:32px 16px; }
    .empty-icon { font-size:1.8em; }
    .toast { bottom:80px; right:16px; left:16px; text-align:center; }
}

/* MOBILE BOTTOM NAV */
.mobile-nav {
    display:none;
    position:fixed; bottom:0; left:0; right:0;
    background:var(--bg-secondary); border-top:1px solid var(--border);
    z-index:200; padding:6px 0 env(safe-area-inset-bottom, 6px);
}
.mobile-nav-inner {
    display:flex; justify-content:space-around; align-items:center;
}
.mobile-nav-item {
    display:flex; flex-direction:column; align-items:center; gap:2px;
    padding:6px 8px; border-radius:8px; cursor:pointer; transition:var(--ease);
    color:var(--text-muted); font-size:0.62em; font-weight:600; text-transform:uppercase; letter-spacing:0.3px;
    position:relative; min-width:52px;
}
.mobile-nav-item svg { width:20px; height:20px; stroke:currentColor; fill:none; stroke-width:2; }
.mobile-nav-item.active { color:var(--brand-gold); }
.mobile-nav-item .mob-badge {
    position:absolute; top:2px; right:4px;
    background:var(--negative); color:#fff; font-size:9px; font-weight:700;
    width:16px; height:16px; border-radius:50%; display:flex; align-items:center; justify-content:center;
}
@media(max-width:768px) {
    .mobile-nav { display:block; }
}

::-webkit-scrollbar{width:6px} ::-webkit-scrollbar-track{background:var(--bg-primary)} ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}

/* DASHBOARD HEADER */
.dashboard-header {
    padding: 20px 32px 16px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-secondary);
}
.dashboard-header-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
}
.dashboard-header-title h2 {
    font-size: 1.3em;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 4px;
}
.dashboard-header-subtitle {
    font-size: 0.82em;
    color: var(--text-secondary);
    margin-top: 2px;
}
.dashboard-header-meta {
    font-size: 0.75em;
    color: var(--text-muted);
    margin-top: 8px;
}
.badge-paper {
    background: rgba(255,171,0,0.15);
    color: var(--warning);
    font-size: 0.72em;
    padding: 4px 10px;
    border-radius: 12px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    display: inline-flex;
    align-items: center;
    white-space: nowrap;
}
.header-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 12px;
    flex-wrap: wrap;
}
.btn-header {
    padding: 7px 16px;
    border-radius: 7px;
    font-size: 0.8em;
    font-weight: 600;
    border: 1px solid var(--border);
    background: var(--bg-hover);
    color: var(--text-secondary);
    cursor: pointer;
    transition: var(--ease);
    display: inline-flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
}
.btn-header:hover {
    border-color: var(--brand-gold);
    color: var(--text-primary);
    background: var(--bg-card);
}
.btn-header:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    border-color: var(--border);
    color: var(--text-muted);
}
.btn-header:disabled:hover {
    background: var(--bg-hover);
    border-color: var(--border);
    color: var(--text-muted);
}
.btn-header .spinner {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 2px solid var(--text-muted);
    border-top-color: var(--brand-gold);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* CONFIRMATION MODAL */
.modal-overlay {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.7); z-index: 10000;
    display: flex; align-items: center; justify-content: center;
    animation: fadeIn 0.15s ease;
}
.modal-card {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 14px; padding: 28px 32px; max-width: 420px; width: 90%;
    box-shadow: 0 16px 48px rgba(0,0,0,0.5);
}
.modal-card h3 { font-size: 1.1em; font-weight: 700; margin-bottom: 12px; }
.modal-card p { font-size: 0.9em; color: var(--text-secondary); line-height: 1.6; margin-bottom: 24px; }
.modal-actions { display: flex; gap: 12px; justify-content: flex-end; }
.btn-modal-cancel { background: var(--bg-hover); color: var(--text-secondary); border: 1px solid var(--border); }
.btn-modal-confirm-danger { background: var(--negative); color: #fff; }
.btn-modal-confirm-approve { background: var(--positive); color: #000; }

/* ACTION REQUIRED PANEL */
.action-panel {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-left: 4px solid var(--brand-gold);
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 28px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.2);
}
.action-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
}
.action-panel-header h3 {
    font-size: 1.05em;
    font-weight: 700;
    color: var(--brand-gold);
    display: flex;
    align-items: center;
    gap: 8px;
}
.action-panel-header .ap-count {
    background: rgba(255,171,0,0.15);
    color: var(--warning);
    font-size: 0.78em;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 12px;
}
.action-panel-empty {
    text-align: center;
    padding: 32px 16px;
    color: var(--text-muted);
}
.action-panel-empty .ape-icon {
    font-size: 2em;
    margin-bottom: 8px;
    color: var(--positive);
    opacity: 0.6;
}
.action-panel-empty .ape-text {
    font-size: 0.92em;
}
.action-rec-card {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px;
    margin-bottom: 14px;
    transition: var(--ease);
}
.action-rec-card:last-child { margin-bottom: 0; }
.action-rec-card:hover { border-color: #3a3a3a; }
.arc-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 12px;
}
.arc-ticker {
    font-size: 1.1em;
    font-weight: 800;
}
.arc-badges {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
}
.arc-dir-badge {
    display: inline-flex;
    align-items: center;
    padding: 3px 10px;
    border-radius: 14px;
    font-size: 0.75em;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.arc-dir-badge.long { background: rgba(0,200,83,0.12); color: var(--positive); }
.arc-dir-badge.short { background: rgba(255,23,68,0.12); color: var(--negative); }
.arc-risk-badge {
    display: inline-flex;
    align-items: center;
    padding: 3px 10px;
    border-radius: 14px;
    font-size: 0.72em;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.4px;
}
.arc-risk-badge.approved { background: rgba(0,200,83,0.1); color: var(--positive); }
.arc-risk-badge.warning { background: rgba(255,171,0,0.1); color: var(--warning); }
.arc-risk-badge.breach { background: rgba(255,23,68,0.1); color: var(--negative); }
.arc-meta {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
    gap: 10px;
    margin-bottom: 12px;
}
.arc-meta-item .am-label {
    font-size: 0.68em;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.arc-meta-item .am-value {
    font-size: 0.9em;
    font-weight: 600;
    margin-top: 2px;
}
.arc-conviction-bar {
    display: flex;
    align-items: center;
    gap: 8px;
}
.arc-conviction-track {
    flex: 1;
    height: 6px;
    background: var(--bg-hover);
    border-radius: 3px;
    overflow: hidden;
    max-width: 80px;
}
.arc-conviction-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s ease;
}
.arc-conviction-fill.high { background: var(--positive); }
.arc-conviction-fill.medium { background: var(--warning); }
.arc-conviction-fill.low { background: var(--negative); }
.arc-rationale {
    font-size: 0.85em;
    color: var(--text-secondary);
    line-height: 1.5;
    padding: 10px 0;
    border-top: 1px solid var(--border);
}
.arc-rationale-text {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.arc-timestamp {
    font-size: 0.72em;
    color: var(--text-muted);
    margin-top: 4px;
}
.arc-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 14px;
    padding-top: 14px;
    border-top: 1px solid var(--border);
    flex-wrap: wrap;
}
.arc-btn-approve {
    padding: 8px 18px;
    border-radius: 7px;
    font-size: 0.82em;
    font-weight: 700;
    border: none;
    cursor: pointer;
    background: var(--positive);
    color: #000;
    transition: var(--ease);
}
.arc-btn-approve:hover { background: #00e05b; transform: translateY(-1px); }
.arc-btn-reject {
    padding: 8px 18px;
    border-radius: 7px;
    font-size: 0.82em;
    font-weight: 700;
    border: 1px solid var(--border);
    cursor: pointer;
    background: var(--bg-hover);
    color: var(--text-secondary);
    transition: var(--ease);
}
.arc-btn-reject:hover { background: var(--negative); color: #fff; border-color: var(--negative); }
.arc-btn-analysis {
    padding: 8px 18px;
    border-radius: 7px;
    font-size: 0.82em;
    font-weight: 600;
    border: 1px solid var(--border);
    cursor: pointer;
    background: transparent;
    color: var(--brand-gold);
    transition: var(--ease);
    margin-left: auto;
}
.arc-btn-analysis:hover { background: rgba(200,169,110,0.08); border-color: var(--brand-gold); }
.arc-detail {
    display: none;
    margin-top: 14px;
    padding: 14px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 0.85em;
    color: var(--text-secondary);
    line-height: 1.6;
}
.arc-detail.expanded { display: block; animation: fadeIn 0.2s ease; }
.arc-detail-section { margin-bottom: 10px; }
.arc-detail-section:last-child { margin-bottom: 0; }
.arc-detail-section strong { color: var(--text-primary); font-size: 0.9em; }
@media(max-width:768px) {
    .action-panel { padding: 16px; }
    .arc-meta { grid-template-columns: repeat(2, 1fr); }
    .arc-actions { flex-direction: column; align-items: stretch; }
    .arc-btn-analysis { margin-left: 0; text-align: center; }
}

/* AGENT CONSENSUS COMPONENT */
.consensus-panel {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 28px;
}
.consensus-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
}
.consensus-header h4 {
    font-size: 0.92em;
    font-weight: 700;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 8px;
}
.consensus-link {
    font-size: 0.8em;
    color: var(--brand-gold);
    cursor: pointer;
    text-decoration: none;
    font-weight: 600;
    transition: var(--ease);
}
.consensus-link:hover {
    color: var(--text-primary);
    text-decoration: underline;
}
.consensus-proposal {
    margin-bottom: 16px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
}
.consensus-proposal:last-child {
    margin-bottom: 0;
    padding-bottom: 0;
    border-bottom: none;
}
.consensus-proposal-id {
    font-size: 0.75em;
    color: var(--text-muted);
    font-weight: 600;
    margin-bottom: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.consensus-votes {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
}
.consensus-vote {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 12px;
    min-width: 160px;
}
.consensus-agent-name {
    font-size: 0.78em;
    font-weight: 600;
    color: var(--text-secondary);
    min-width: 70px;
}
.consensus-stance-badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.7em;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}
.consensus-stance-badge.support { background: rgba(91,138,181,0.12); color: var(--steel-blue); }
.consensus-stance-badge.challenge { background: rgba(255,23,68,0.12); color: var(--negative); }
.consensus-stance-badge.defend { background: rgba(160,160,160,0.1); color: var(--text-secondary); }
.consensus-stance-badge.neutral { background: rgba(160,160,160,0.1); color: var(--text-secondary); }
.consensus-confidence-bar {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-left: auto;
}
.consensus-confidence-track {
    width: 48px;
    height: 5px;
    background: var(--bg-hover);
    border-radius: 3px;
    overflow: hidden;
}
.consensus-confidence-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s ease;
}
.consensus-confidence-fill.high { background: var(--positive); }
.consensus-confidence-fill.medium { background: var(--warning); }
.consensus-confidence-fill.low { background: var(--negative); }
.consensus-confidence-label {
    font-size: 0.68em;
    color: var(--text-muted);
    font-weight: 600;
    min-width: 22px;
    text-align: right;
}
.consensus-warning {
    background: rgba(255,171,0,0.08);
    border: 1px solid rgba(255,171,0,0.25);
    border-radius: 8px;
    padding: 10px 14px;
    margin-top: 12px;
    font-size: 0.82em;
    color: var(--warning);
    display: flex;
    align-items: center;
    gap: 8px;
}
.consensus-empty {
    text-align: center;
    padding: 20px 16px;
    color: var(--text-muted);
    font-size: 0.88em;
}
@media(max-width:768px) {
    .consensus-panel { padding: 16px; }
    .consensus-votes { flex-direction: column; gap: 8px; }
    .consensus-vote { min-width: unset; }
}

/* SYSTEM HEALTH PANEL */
.system-health-panel {
    display: flex;
    align-items: center;
    gap: 20px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 20px;
    margin-top: 24px;
    flex-wrap: wrap;
}
.system-health-panel .shp-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.82em;
}
.system-health-panel .shp-label {
    color: var(--text-muted);
    font-weight: 600;
    font-size: 0.85em;
    text-transform: uppercase;
    letter-spacing: 0.4px;
}
.system-health-panel .shp-value {
    color: var(--text-secondary);
    font-weight: 500;
}
.health-indicator {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
}
.health-indicator.fresh { background: var(--positive); }
.health-indicator.aging { background: var(--warning); }
.health-indicator.stale { background: var(--negative); }
.health-indicator.unknown { background: var(--text-muted); }
.shp-stale-warning {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--warning);
    font-size: 0.82em;
    font-weight: 600;
    background: rgba(255,171,0,0.08);
    border: 1px solid rgba(255,171,0,0.2);
    border-radius: 6px;
    padding: 6px 12px;
    margin-left: auto;
}
@media(max-width:768px) {
    .system-health-panel {
        flex-direction: column;
        align-items: flex-start;
        gap: 10px;
        padding: 12px 16px;
    }
    .shp-stale-warning { margin-left: 0; }
}

/* SIDEBAR REFRESH BUTTON IMPROVEMENTS */
.sidebar-refresh-status {
    font-size: 0.72em;
    color: var(--text-muted);
    margin-top: 4px;
    text-align: center;
}
.sidebar-footer .btn-mark .spinner {
    display: inline-block;
    width: 10px;
    height: 10px;
    border: 2px solid var(--text-muted);
    border-top-color: var(--brand-gold);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-right: 4px;
    vertical-align: middle;
}

/* ACCESSIBILITY: FOCUS VISIBLE STYLES */
:focus-visible {
    outline: 2px solid var(--brand-gold);
    outline-offset: 2px;
}
button:focus-visible,
.btn:focus-visible,
.btn-header:focus-visible,
.btn-review:focus-visible,
.arc-btn-approve:focus-visible,
.arc-btn-reject:focus-visible,
.arc-btn-analysis:focus-visible,
.nav-item:focus-visible,
.mobile-nav-item:focus-visible,
.chart-range-btn:focus-visible,
.metric-card.clickable:focus-visible,
.position-filter-input:focus-visible,
.chat-input:focus-visible,
.chat-send:focus-visible {
    outline: 2px solid var(--brand-gold);
    outline-offset: 2px;
}

/* ACCESSIBILITY: PREFERS REDUCED MOTION */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
    }
}

/* ACCESSIBILITY: Ensure clickable non-button elements are keyboard accessible */
.nav-item[role="button"],
.mobile-nav-item[role="button"],
.metric-card.clickable[role="button"] {
    cursor: pointer;
}

/* COLOR CONTRAST FIX: bump text-muted for body text areas */
.position-detail-panel .pdp-value,
.arc-rationale-text,
.pending-rationale {
    color: #9a9a9a;
}
</style>
"""


def build_sidebar() -> str:
    return """
<nav class="sidebar" aria-label="Main navigation">
    <div class="sidebar-brand">
        <h1>Agentic Trading</h1>
        <div class="sub">Portfolio System</div>
    </div>
    <div class="sidebar-nav">
        <div class="nav-label">Dashboard</div>
        <div class="nav-item active" data-tab="overview" onclick="switchTab('overview')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('overview');}">Overview</div>
        <div class="nav-item" data-tab="pending" onclick="switchTab('pending')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('pending');}">
            Pending Orders <span class="badge-count" id="pending-count" style="display:none;">0</span>
        </div>
        <div class="nav-item" data-tab="positions" onclick="switchTab('positions')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('positions');}">Positions</div>
        <div class="nav-item" data-tab="journal" onclick="switchTab('journal')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('journal');}">Trade Journal</div>

        <div class="nav-label">Analysis</div>
        <div class="nav-item" data-tab="debate" onclick="switchTab('debate')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('debate');}">Agent Debate</div>
        <div class="nav-item" data-tab="risk" onclick="switchTab('risk')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('risk');}">Risk</div>
        <div class="nav-item" data-tab="technical" onclick="switchTab('technical')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('technical');}">Technical</div>

        <div class="nav-label">History</div>
        <div class="nav-item" data-tab="timeline" onclick="switchTab('timeline')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('timeline');}">Cycle History</div>

        <div class="nav-label">Assistant</div>
        <div class="nav-item" data-tab="chat" onclick="switchTab('chat')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('chat');}">Ask Agent</div>
    </div>
    <div class="sidebar-footer">
        <button class="btn btn-mark" id="sidebar-refresh-btn" onclick="handleSidebarRefresh()" style="width:100%;margin-bottom:4px;" aria-label="Refresh market prices">Refresh Prices</button>
        <div class="sidebar-refresh-status" id="sidebar-refresh-status">Auto-refreshes every 30s</div>
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
    <div id="dashboard-header"></div>
    <div class="content">
        <div class="panel active" id="panel-overview"></div>
        <div class="panel" id="panel-pending"></div>
        <div class="panel" id="panel-positions"></div>
        <div class="panel" id="panel-journal"></div>
        <div class="panel" id="panel-debate"></div>
        <div class="panel" id="panel-risk"></div>
        <div class="panel" id="panel-technical"></div>
        <div class="panel" id="panel-timeline"></div>
        <div class="panel" id="panel-chat"></div>
    </div>
</div>

<!-- MOBILE BOTTOM NAV -->
<nav class="mobile-nav" aria-label="Mobile navigation">
    <div class="mobile-nav-inner">
        <div class="mobile-nav-item active" data-tab="overview" onclick="switchTab('overview')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('overview');}">
            <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
            Home
        </div>
        <div class="mobile-nav-item" data-tab="pending" onclick="switchTab('pending')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('pending');}">
            <svg viewBox="0 0 24 24"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
            Orders
            <span class="mob-badge" id="mob-pending-count" style="display:none;">0</span>
        </div>
        <div class="mobile-nav-item" data-tab="positions" onclick="switchTab('positions')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('positions');}">
            <svg viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
            Book
        </div>
        <div class="mobile-nav-item" data-tab="debate" onclick="switchTab('debate')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('debate');}">
            <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
            Debate
        </div>
        <div class="mobile-nav-item" data-tab="journal" onclick="switchTab('journal')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('journal');}">
            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            History
        </div>
    </div>
</nav>

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
        showToast(`Marked to market — NAV: ${{formatCurrency(r.nav)}}`, 'success');
        await refreshAll();
    }}
}}

// ─── CONFIRMATION MODAL ──────────────────────────────────────────────────────
function showConfirmModal(title, message, onConfirm, type) {{
    type = type || 'danger';
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'modal-title');
    const confirmClass = type === 'approve' ? 'btn-modal-confirm-approve' : 'btn-modal-confirm-danger';
    overlay.innerHTML = `
        <div class="modal-card">
            <h3 id="modal-title">${{title}}</h3>
            <p>${{message}}</p>
            <div class="modal-actions">
                <button class="btn btn-modal-cancel" data-modal-cancel>Cancel</button>
                <button class="btn ${{confirmClass}}" data-modal-confirm>Confirm</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    document.body.style.overflow = 'hidden';

    // Focus trap: get all focusable elements in modal
    const focusableEls = overlay.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    const firstFocusable = focusableEls[0];
    const lastFocusable = focusableEls[focusableEls.length - 1];

    // Focus the cancel button initially
    if (firstFocusable) firstFocusable.focus();

    function dismiss() {{
        overlay.remove();
        document.body.style.overflow = '';
        document.removeEventListener('keydown', onKey);
    }}
    function onKey(e) {{
        if (e.key === 'Escape') dismiss();
        // Focus trap: Tab cycles within modal
        if (e.key === 'Tab') {{
            if (e.shiftKey) {{
                if (document.activeElement === firstFocusable) {{
                    e.preventDefault();
                    lastFocusable.focus();
                }}
            }} else {{
                if (document.activeElement === lastFocusable) {{
                    e.preventDefault();
                    firstFocusable.focus();
                }}
            }}
        }}
    }}
    document.addEventListener('keydown', onKey);

    overlay.addEventListener('click', function(e) {{
        if (e.target === overlay) dismiss();
    }});
    overlay.querySelector('[data-modal-cancel]').addEventListener('click', dismiss);
    overlay.querySelector('[data-modal-confirm]').addEventListener('click', function() {{
        onConfirm();
        dismiss();
    }});
}}

function acceptOrder(orderId) {{
    showConfirmModal('Confirm Trade', 'Accept and execute this trade?', async function() {{
        const btn = document.querySelector(`[data-accept-id="${{orderId}}"]`);
        if (btn) {{ btn.disabled = true; btn.textContent = 'Executing...'; }}
        const r = await apiPost(`/api/accept/${{orderId}}`);
        if (r) {{
            showToast(`Accepted: ${{r.ticker}} @ $${{r.entry_price?.toFixed(2)}}`, 'success');
            await refreshAll();
        }}
        if (btn) {{ btn.disabled = false; btn.textContent = 'Accept'; }}
    }}, 'approve');
}}

function denyOrder(orderId) {{
    showConfirmModal('Reject Trade', 'Reject this recommendation?', async function() {{
        const btn = document.querySelector(`[data-deny-id="${{orderId}}"]`);
        if (btn) {{ btn.disabled = true; btn.textContent = 'Rejecting...'; }}
        const r = await apiPost(`/api/deny/${{orderId}}`);
        if (r) {{
            showToast(`Denied: ${{r.proposal_id}}`, 'success');
            await refreshAll();
        }}
        if (btn) {{ btn.disabled = false; btn.textContent = 'Deny'; }}
    }}, 'danger');
}}

function closePosition(ticker) {{
    showConfirmModal('Close Position', `Close position in ${{ticker}} at market?`, async function() {{
        const r = await apiPost(`/api/close/${{ticker}}`);
        if (r) {{
            showToast(`Closed ${{ticker}} — P&L: ${{(r.realized_pnl_pct*100).toFixed(2)}}%`, r.realized_pnl_pct >= 0 ? 'success' : 'error');
            await refreshAll();
        }}
    }}, 'danger');
}}

// ─── RENDER ─────────────────────────────────────────────────────────────────
function renderAll() {{
    renderDashboardHeader();
    renderTopbar();
    renderOverview();
    renderPending();
    renderPositions();
    renderJournal();
    renderDebate();
    renderRisk();
    renderTechnical();
    renderTimeline();
    renderChat();
    updatePendingBadge();
}}

function renderDashboardHeader() {{
    const container = document.getElementById('dashboard-header');
    if (!container) return;

    const lastMarked = state.book.last_marked;
    let lastUpdatedStr = 'Never';
    if (lastMarked) {{
        try {{
            const d = new Date(lastMarked);
            lastUpdatedStr = d.toLocaleString('en-US', {{
                month: 'short', day: 'numeric', year: 'numeric',
                hour: 'numeric', minute: '2-digit', hour12: true
            }});
        }} catch(e) {{
            lastUpdatedStr = lastMarked;
        }}
    }}

    container.innerHTML = `
        <div class="dashboard-header">
            <div class="dashboard-header-top">
                <div class="dashboard-header-title">
                    <h2>Portfolio Overview</h2>
                    <div class="dashboard-header-subtitle">Multi-Sector Hedged L/S | $10M Initial NAV</div>
                    <div class="dashboard-header-meta">Last updated: ${{lastUpdatedStr}}</div>
                </div>
                <span class="badge-paper">PAPER TRADING</span>
            </div>
            <div class="header-actions">
                <button class="btn-header" id="btn-refresh-data" onclick="handleRefreshData()">
                    Refresh Data
                </button>
                <button class="btn-header" onclick="showConfirmModal('Run Agent Cycle', 'This will trigger a full agent analysis and trade proposal cycle. Continue?', function() {{ console.log('Agent cycle triggered'); showToast('Agent cycle started (placeholder)', 'info'); }}, 'approve')">
                    Run Agent Cycle
                </button>
                <button class="btn-header" disabled title="Coming soon">
                    Export Report
                </button>
            </div>
        </div>
    `;
}}

async function handleRefreshData() {{
    const btn = document.getElementById('btn-refresh-data');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Refreshing...';
    await markToMarket();
    btn.disabled = false;
    btn.innerHTML = 'Refresh Data';
}}

// ─── SIDEBAR REFRESH HANDLER ─────────────────────────────────────────────────
async function handleSidebarRefresh() {{
    const btn = document.getElementById('sidebar-refresh-btn');
    const statusEl = document.getElementById('sidebar-refresh-status');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Refreshing...';
    await markToMarket();
    btn.disabled = false;
    btn.innerHTML = 'Refresh Prices';
    // Update status with last refresh time
    const now = new Date();
    const hh = now.getHours().toString().padStart(2, '0');
    const mm = now.getMinutes().toString().padStart(2, '0');
    if (statusEl) {{
        statusEl.textContent = 'Last: ' + hh + ':' + mm;
    }}
}}

// ─── SYSTEM HEALTH PANEL ─────────────────────────────────────────────────────
function renderSystemHealth() {{
    const lastMarked = state.book.last_marked || null;
    const logs = state.logs || [];

    // Last data refresh time + freshness
    let refreshTimeStr = 'Unknown';
    let refreshFreshness = 'unknown';
    if (lastMarked) {{
        try {{
            const d = new Date(lastMarked);
            refreshTimeStr = d.toLocaleString('en-US', {{ month:'short', day:'numeric', hour:'numeric', minute:'2-digit', hour12:true }});
            const diffHours = (Date.now() - d.getTime()) / (1000 * 60 * 60);
            if (diffHours < 4) refreshFreshness = 'fresh';
            else if (diffHours < 24) refreshFreshness = 'aging';
            else refreshFreshness = 'stale';
        }} catch(e) {{
            refreshFreshness = 'unknown';
        }}
    }}

    // Last cycle time (from logs)
    let lastCycleStr = 'Unknown';
    if (logs.length > 0) {{
        const lastLog = logs[logs.length - 1];
        const ts = lastLog.timestamp || lastLog.completed_at || '';
        if (ts) {{
            try {{
                const d = new Date(ts);
                lastCycleStr = d.toLocaleString('en-US', {{ month:'short', day:'numeric', hour:'numeric', minute:'2-digit', hour12:true }});
            }} catch(e) {{
                lastCycleStr = ts;
            }}
        }}
    }}

    // Alerts count
    let alertCount = 0;
    let alertSeverity = 'none';
    // Check for risk warnings in latest risk assessment
    if (state.risks && state.risks.length > 0) {{
        const latestRisk = state.risks[state.risks.length - 1];
        const warnings = latestRisk.risk_warnings || [];
        alertCount = warnings.length;
        if (alertCount > 0) {{
            alertSeverity = warnings.some(w => w.toLowerCase().includes('breach') || w.toLowerCase().includes('critical')) ? 'stale' : 'aging';
        }}
    }}

    // Stale data warning (>24h on weekday)
    const isDataStale = isStale(lastMarked, 24);
    let staleWarningHtml = '';
    if (isDataStale) {{
        staleWarningHtml = `<div class="shp-stale-warning" role="alert">
            &#9888; Data may be stale
        </div>`;
    }}

    // Alert indicator class
    const alertDotClass = alertCount === 0 ? 'fresh' : alertSeverity;

    return `<div class="system-health-panel" role="region" aria-label="System health status">
        <div class="shp-item">
            <span class="health-indicator ${{refreshFreshness}}" aria-hidden="true"></span>
            <span class="shp-label">Last Refresh</span>
            <span class="shp-value">${{refreshTimeStr}}</span>
        </div>
        <div class="shp-item">
            <span class="health-indicator ${{logs.length > 0 ? 'fresh' : 'unknown'}}" aria-hidden="true"></span>
            <span class="shp-label">Last Cycle</span>
            <span class="shp-value">${{lastCycleStr}}</span>
        </div>
        <div class="shp-item">
            <span class="health-indicator ${{alertDotClass}}" aria-hidden="true"></span>
            <span class="shp-label">Alerts</span>
            <span class="shp-value">${{alertCount}}</span>
        </div>
        ${{staleWarningHtml}}
    </div>`;
}}

// ─── KPI GRID (10 CARDS) ─────────────────────────────────────────────────────
function renderKPIGrid() {{
    const summary = computePortfolioSummary(state.book, state.history, state.pending);
    if (!summary) return renderKPIGridSkeleton();

    const cards = [
        {{
            label: 'NAV',
            value: formatCurrency(summary.nav),
            sub: 'Initial: ' + formatCurrency(summary.initialNav),
            trend: trendIndicator(summary.nav - summary.initialNav),
            colorClass: 'neutral',
            colorStyle: 'color:var(--brand-gold);',
            ariaLabel: 'Net Asset Value: ' + formatCurrency(summary.nav),
            clickable: false,
        }},
        {{
            label: 'Daily P&L',
            value: formatCurrency(summary.dailyPnlDollars),
            sub: formatPctSigned(summary.dailyPnlPct),
            trend: trendIndicator(summary.dailyPnlDollars),
            colorClass: pnlState(summary.dailyPnlDollars),
            colorStyle: '',
            ariaLabel: 'Daily Profit and Loss: ' + formatCurrency(summary.dailyPnlDollars) + ' (' + formatPctSigned(summary.dailyPnlPct) + ')',
            clickable: false,
        }},
        {{
            label: 'Total P&L',
            value: formatPctSigned(summary.totalPnlPct),
            sub: formatCurrency(summary.totalPnlDollars) + ' since inception',
            trend: trendIndicator(summary.totalPnlDollars),
            colorClass: pnlState(summary.totalPnlDollars),
            colorStyle: '',
            ariaLabel: 'Total Profit and Loss: ' + formatPctSigned(summary.totalPnlPct) + ' (' + formatCurrency(summary.totalPnlDollars) + ')',
            clickable: false,
        }},
        {{
            label: 'Cash',
            value: (summary.cashPct * 100).toFixed(1) + '%',
            sub: formatCurrency(summary.cashDollars) + ' available',
            trend: '',
            colorClass: 'neutral',
            colorStyle: 'color:var(--info-blue);',
            ariaLabel: 'Cash: ' + (summary.cashPct * 100).toFixed(1) + '% (' + formatCurrency(summary.cashDollars) + ')',
            clickable: false,
        }},
        {{
            label: 'Gross Exposure',
            value: (summary.grossExposure * 100).toFixed(1) + '%',
            sub: formatCurrency(summary.nav * summary.grossExposure) + ' notional',
            trend: '',
            colorClass: summary.grossExposure > 2.5 ? 'negative' : summary.grossExposure > 1.5 ? 'neutral' : 'neutral',
            colorStyle: summary.grossExposure > 2.5 ? 'color:var(--negative);' : '',
            ariaLabel: 'Gross Exposure: ' + (summary.grossExposure * 100).toFixed(1) + '%',
            clickable: false,
        }},
        {{
            label: 'Net Exposure',
            value: (summary.netExposure >= 0 ? '+' : '') + (summary.netExposure * 100).toFixed(1) + '%',
            sub: (summary.netExposure >= 0 ? 'Net long' : 'Net short'),
            trend: '',
            colorClass: 'neutral',
            colorStyle: 'color:var(--info-blue);',
            ariaLabel: 'Net Exposure: ' + (summary.netExposure * 100).toFixed(1) + '%',
            clickable: false,
        }},
        {{
            label: 'Drawdown',
            value: summary.drawdownPct === 0 ? '0.00%' : '-' + (summary.drawdownPct * 100).toFixed(2) + '%',
            sub: 'Peak NAV: ' + formatCurrency(summary.peakNav),
            trend: summary.drawdownPct > 0 ? '▼' : '—',
            colorClass: summary.drawdownPct > 0.05 ? 'negative' : summary.drawdownPct > 0 ? 'neutral' : 'neutral',
            colorStyle: summary.drawdownPct > 0.05 ? 'color:var(--negative);' : '',
            ariaLabel: 'Drawdown: ' + (summary.drawdownPct * 100).toFixed(2) + '% from peak NAV of ' + formatCurrency(summary.peakNav),
            clickable: false,
        }},
        {{
            label: 'Risk Utilization',
            value: (summary.riskUtilization * 100).toFixed(0) + '%',
            sub: (summary.grossExposure).toFixed(2) + 'x / 3.0x max',
            trend: '',
            colorClass: summary.riskUtilization > 0.9 ? 'negative' : summary.riskUtilization > 0.7 ? 'neutral' : 'neutral',
            colorStyle: summary.riskUtilization > 0.9 ? 'color:var(--negative);' : summary.riskUtilization > 0.7 ? 'color:var(--warning);' : '',
            ariaLabel: 'Risk Utilization: ' + (summary.riskUtilization * 100).toFixed(0) + '% of maximum allowed leverage',
            clickable: false,
        }},
        {{
            label: 'Active Positions',
            value: String(summary.activePositions),
            sub: summary.activePositions === 0 ? 'No open trades' : summary.activePositions + ' open trade' + (summary.activePositions !== 1 ? 's' : ''),
            trend: '',
            colorClass: 'neutral',
            colorStyle: 'color:var(--info-blue);',
            ariaLabel: 'Active Positions: ' + summary.activePositions,
            clickable: false,
        }},
        {{
            label: 'Pending Recommendations',
            value: String(summary.pendingCount),
            sub: summary.pendingCount === 0 ? 'All caught up' : summary.pendingCount + ' awaiting review',
            trend: '',
            colorClass: summary.pendingCount > 0 ? 'neutral' : 'neutral',
            colorStyle: summary.pendingCount > 0 ? 'color:var(--warning);' : '',
            ariaLabel: 'Pending Recommendations: ' + summary.pendingCount,
            clickable: summary.pendingCount > 0,
        }},
    ];

    let html = '<div class="kpi-grid">';
    for (const card of cards) {{
        const clickAttr = card.clickable ? ' onclick="switchTab(\\'pending\\')"' : '';
        const clickClass = card.clickable ? ' clickable' : '';
        const valueStyle = card.colorStyle || '';
        const colorCls = card.colorClass && card.colorClass !== 'neutral' ? ' ' + card.colorClass : '';
        html += `<div class="metric-card${{clickClass}}" role="region" aria-label="${{card.ariaLabel}}"${{clickAttr}}>`;
        html += `<div class="metric-label">${{card.label}}</div>`;
        html += `<div class="metric-value${{colorCls}}" style="${{valueStyle}}">${{card.value}}<span class="trend-indicator">${{card.trend}}</span></div>`;
        html += `<div class="metric-sub">${{card.sub}}</div>`;
        html += '</div>';
    }}
    html += '</div>';
    return html;
}}

function renderKPIGridSkeleton() {{
    let html = '<div class="kpi-grid">';
    const labels = ['NAV','Daily P&L','Total P&L','Cash','Gross Exposure','Net Exposure','Drawdown','Risk Utilization','Active Positions','Pending Recommendations'];
    for (const label of labels) {{
        html += `<div class="metric-card" role="region" aria-label="${{label}}: loading">`;
        html += `<div class="metric-label">${{label}}</div>`;
        html += `<div class="skeleton-pulse"></div>`;
        html += `<div class="metric-sub" style="color:var(--text-muted);">Loading...</div>`;
        html += '</div>';
    }}
    html += '</div>';
    return html;
}}

function trendIndicator(val) {{
    if (val == null || val === 0) return '—';
    return val > 0 ? '▲' : '▼';
}}

function renderTopbar() {{
    const b = state.book;
    const nav = b.nav || b.initial_nav || 10000000;
    const initial = b.initial_nav || 10000000;
    const pnl = (nav - initial) / initial;
    const activePos = (b.positions || []).filter(p => p.status === 'active').length;

    document.getElementById('topbar-nav').textContent = formatCurrency(nav);
    const pnlEl = document.getElementById('topbar-pnl');
    pnlEl.textContent = formatPctSigned(pnl);
    pnlEl.className = 'value ' + pnlState(pnl);
    document.getElementById('topbar-cash').textContent = (b.cash_pct * 100).toFixed(0) + '%';
    document.getElementById('topbar-pos').textContent = activePos;
}}

function renderOverview() {{
    const b = state.book;
    const activePos = (b.positions || []).filter(p => p.status === 'active');

    let html = renderKPIGrid();

    // Action Required panel (below KPI grid)
    html += renderActionRequired();

    // Agent Consensus panel (after Action Required)
    html += renderAgentConsensus();

    // Equity Chart (with range selector, reference line, tooltips, drawdown toggle)
    html += `<div class="section-title">Equity Curve</div>`;
    html += renderEquityChart();

    // Quick position summary
    if (activePos.length) {{
        html += `<div class="section-title">Position Summary</div><table class="data-table"><thead><tr><th>Ticker</th><th>Direction</th><th>Hedge</th><th>Today</th><th>Total P&L</th><th>Size</th><th></th></tr></thead><tbody>`;
        for (const p of activePos) {{
            const cpnl = p.combined_pnl_pct;
            const dailyChg = p.daily_change_pct || 0;
            html += `<tr><td style="font-weight:600;">${{p.ticker}}</td><td>${{p.direction?.toUpperCase()}}</td><td>${{p.hedge_ticker||'—'}}</td><td class="${{pnlState(dailyChg)}}" style="font-weight:600;">${{formatPctSigned(dailyChg)}}</td><td class="${{pnlState(cpnl)}}" style="font-weight:700;">${{formatPctSigned(cpnl)}}</td><td>${{(p.size_pct_nav*100).toFixed(1)}}%</td><td><button class="btn btn-close" onclick="closePosition('${{p.ticker}}')">Close</button></td></tr>`;
        }}
        html += `</tbody></table>`;
    }}

    // System Health Panel (compact row at bottom of overview)
    html += renderSystemHealth();

    document.getElementById('panel-overview').innerHTML = html;
}}

// ─── ACTION REQUIRED PANEL ──────────────────────────────────────────────────
function renderActionRequired() {{
    // Empty state: show polished message when no pending orders
    if (!state.pending || state.pending.length === 0) {{
        return `
        <div class="action-panel" style="border-left-color:var(--positive);">
            <div class="action-panel-empty">
                <div class="ape-icon">&#10003;</div>
                <div class="ape-text">All caught up — no pending decisions</div>
            </div>
        </div>`;
    }}

    let html = `<div class="action-panel">`;
    html += `<div class="action-panel-header">
        <h3>&#9888; Action Required</h3>
        <span class="ap-count">${{state.pending.length}} pending</span>
    </div>`;

    for (let i = 0; i < state.pending.length; i++) {{
        const rec = state.pending[i];
        const id = rec.order_id || rec.proposal_id || ('rec-' + i);
        const ticker = rec.ticker || '—';
        const direction = (rec.direction || '').toLowerCase();
        const dirDisplay = direction.toUpperCase();
        const dirClass = direction === 'long' ? 'long' : 'short';

        // Current price (from _proposal or book if enriched)
        const currentPrice = rec.current_price || rec._current_price || null;

        // Size
        const sizePct = rec.size_pct_nav != null ? (rec.size_pct_nav * 100).toFixed(1) + '% NAV' : '—';

        // Conviction bar
        const conviction = rec.conviction || 0;
        const convictionPct = (conviction / 10) * 100;
        const convClass = classifyConfidence(conviction);

        // Rationale
        const rationale = rec.pm_rationale || 'No rationale provided.';

        // Risk classification
        const risk = rec._risk || {{}};
        const riskDecision = risk.decision || '';
        const riskClass = classifyRisk(riskDecision);
        const riskLabel = riskDecision ? riskDecision.toUpperCase() : 'PENDING';

        // Timestamp (from order or proposal)
        const timestamp = rec.timestamp || rec.created_at || '';
        let tsDisplay = '';
        if (timestamp) {{
            try {{
                const d = new Date(timestamp);
                tsDisplay = d.toLocaleString('en-US', {{ month:'short', day:'numeric', hour:'numeric', minute:'2-digit', hour12:true }});
            }} catch(e) {{
                tsDisplay = timestamp;
            }}
        }}

        // Proposal details for "View Analysis"
        const proposal = rec._proposal || {{}};
        const thesis = proposal.thesis_summary || proposal.thesisSummary || '';
        const variant = proposal.variant_perception || proposal.variantPerception || '';
        const catalyst = proposal.catalyst || '';
        const keyRisks = proposal.key_risks || proposal.keyRisks || [];
        const risksStr = Array.isArray(keyRisks) ? keyRisks.join('; ') : (keyRisks || '');

        html += `<div class="action-rec-card" id="arc-${{id}}">`;

        // Top row: ticker + badges
        html += `<div class="arc-top">
            <span class="arc-ticker">${{ticker}}</span>
            <div class="arc-badges">
                <span class="arc-dir-badge ${{dirClass}}">${{dirDisplay}}</span>
                <span class="arc-risk-badge ${{riskClass}}">${{riskLabel}}</span>
            </div>
        </div>`;

        // Meta grid: current price, size, conviction, timestamp
        html += `<div class="arc-meta">`;
        if (currentPrice != null) {{
            html += `<div class="arc-meta-item"><div class="am-label">Current Price</div><div class="am-value">${{formatCurrency(currentPrice, 2)}}</div></div>`;
        }}
        html += `<div class="arc-meta-item"><div class="am-label">Size</div><div class="am-value">${{sizePct}}</div></div>`;
        html += `<div class="arc-meta-item"><div class="am-label">Conviction</div><div class="am-value">
            <div class="arc-conviction-bar">
                <span>${{conviction}}/10</span>
                <div class="arc-conviction-track"><div class="arc-conviction-fill ${{convClass}}" style="width:${{convictionPct}}%;"></div></div>
            </div>
        </div></div>`;
        if (tsDisplay) {{
            html += `<div class="arc-meta-item"><div class="am-label">Timestamp</div><div class="am-value" style="font-size:0.82em;">${{tsDisplay}}</div></div>`;
        }}
        html += `</div>`;

        // Rationale (truncated)
        html += `<div class="arc-rationale"><div class="arc-rationale-text">${{escapeHtml(rationale)}}</div></div>`;

        // Actions: Approve, Reject, View Analysis
        html += `<div class="arc-actions">
            <button class="arc-btn-approve" data-accept-id="${{id}}" onclick="acceptOrder('${{id}}')" aria-label="Approve trade for ${{ticker}}">Approve</button>
            <button class="arc-btn-reject" data-deny-id="${{id}}" onclick="denyOrder('${{id}}')" aria-label="Reject trade for ${{ticker}}">Reject</button>
            <button class="arc-btn-analysis" onclick="toggleAnalysisDetail('${{id}}')" aria-label="View analysis for ${{ticker}}">View Analysis</button>
        </div>`;

        // Expandable detail section
        html += `<div class="arc-detail" id="arc-detail-${{id}}">`;
        if (thesis) html += `<div class="arc-detail-section"><strong>Thesis:</strong> ${{escapeHtml(thesis)}}</div>`;
        if (variant) html += `<div class="arc-detail-section"><strong>Variant Perception:</strong> ${{escapeHtml(variant)}}</div>`;
        if (catalyst) html += `<div class="arc-detail-section"><strong>Catalyst:</strong> ${{escapeHtml(catalyst)}}</div>`;
        if (risksStr) html += `<div class="arc-detail-section"><strong>Key Risks:</strong> ${{escapeHtml(risksStr)}}</div>`;
        if (!thesis && !variant && !catalyst && !risksStr) {{
            html += `<div class="arc-detail-section" style="color:var(--text-muted);">No additional analysis available for this recommendation.</div>`;
        }}
        html += `</div>`;

        html += `</div>`;  // .action-rec-card
    }}

    html += `</div>`;  // .action-panel
    return html;
}}

function toggleAnalysisDetail(orderId) {{
    const el = document.getElementById('arc-detail-' + orderId);
    if (!el) return;
    el.classList.toggle('expanded');
}}

// ─── AGENT CONSENSUS COMPONENT ───────────────────────────────────────────────
function renderAgentConsensus() {{
    // Handle missing debate data gracefully
    if (!state.debates || state.debates.length === 0) {{
        return `<div class="consensus-panel">
            <div class="consensus-header">
                <h4>Agent Consensus</h4>
            </div>
            <div class="consensus-empty">No debate data available</div>
        </div>`;
    }}

    // Find the most recent proposal_id(s) from debates
    const proposalIds = [...new Set(state.debates.map(d => d.proposal_id).filter(Boolean))];
    if (proposalIds.length === 0) {{
        return `<div class="consensus-panel">
            <div class="consensus-header">
                <h4>Agent Consensus</h4>
            </div>
            <div class="consensus-empty">No debate data available</div>
        </div>`;
    }}

    // Get the most recent 1-2 proposals (last entries in the array are most recent)
    const recentProposals = proposalIds.slice(-2);

    let proposalsHtml = '';

    for (const proposalId of recentProposals) {{
        // Filter debates for this proposal
        const proposalDebates = state.debates.filter(d => d.proposal_id === proposalId);

        // Group by agent_id and take the latest round per agent
        const agentMap = {{}};
        for (const d of proposalDebates) {{
            const agentId = d.agent_id || 'unknown';
            if (!agentMap[agentId] || (d.round || 0) > (agentMap[agentId].round || 0)) {{
                agentMap[agentId] = d;
            }}
        }}

        // Build vote badges for each agent
        let votesHtml = '';
        const stances = [];

        for (const [agentId, debate] of Object.entries(agentMap)) {{
            const agentName = agentId.replace(/_/g, ' ').replace(/\\b\\w/g, c => c.toUpperCase());
            const stance = (debate.stance || 'neutral').toLowerCase();
            stances.push(stance);
            const conviction = debate.revised_conviction || 0;
            const convPct = (conviction / 10) * 100;
            const convClass = classifyConfidence(conviction);

            votesHtml += `<div class="consensus-vote">
                <span class="consensus-agent-name">${{agentName}}</span>
                <span class="consensus-stance-badge ${{stance}}">${{stance.toUpperCase()}}</span>
                <div class="consensus-confidence-bar">
                    <div class="consensus-confidence-track">
                        <div class="consensus-confidence-fill ${{convClass}}" style="width:${{convPct}}%;"></div>
                    </div>
                    <span class="consensus-confidence-label">${{conviction}}</span>
                </div>
            </div>`;
        }}

        // Add Technical score if available for this proposal
        const matchingScore = state.scores.find(s => s.proposal_id && s.proposal_id.includes(proposalId.replace(/^(fund_|macro_|tech_)/, '')));
        const latestScore = matchingScore || (state.scores.length > 0 ? state.scores[state.scores.length - 1] : null);
        if (latestScore && latestScore.technical_score != null) {{
            const techScore = latestScore.technical_score;
            const techPct = (techScore / 10) * 100;
            const techClass = classifyConfidence(techScore);
            votesHtml += `<div class="consensus-vote">
                <span class="consensus-agent-name">Technical</span>
                <span class="consensus-stance-badge ${{techScore >= 7 ? 'support' : techScore >= 4 ? 'neutral' : 'challenge'}}">${{techScore >= 7 ? 'BULLISH' : techScore >= 4 ? 'NEUTRAL' : 'BEARISH'}}</span>
                <div class="consensus-confidence-bar">
                    <div class="consensus-confidence-track">
                        <div class="consensus-confidence-fill ${{techClass}}" style="width:${{techPct}}%;"></div>
                    </div>
                    <span class="consensus-confidence-label">${{techScore}}</span>
                </div>
            </div>`;
        }}

        // Add Risk decision if available
        const matchingRisk = state.risks.find(r => r.proposal_id && r.proposal_id.includes(proposalId.replace(/^(fund_|macro_|tech_)/, '')));
        const latestRisk = matchingRisk || (state.risks.length > 0 ? state.risks[state.risks.length - 1] : null);
        if (latestRisk && latestRisk.decision) {{
            const riskDecision = latestRisk.decision.toLowerCase();
            const riskStance = riskDecision.includes('approved') || riskDecision.includes('proceed') ? 'support' : 'challenge';
            votesHtml += `<div class="consensus-vote">
                <span class="consensus-agent-name">Risk</span>
                <span class="consensus-stance-badge ${{riskStance}}">${{latestRisk.decision.toUpperCase()}}</span>
                <div class="consensus-confidence-bar"></div>
            </div>`;
        }}

        // Detect disagreement: one challenges while others support
        const hasChallenge = stances.includes('challenge');
        const hasSupport = stances.includes('support') || stances.includes('defend');
        const hasDisagreement = hasChallenge && hasSupport;

        let warningHtml = '';
        if (hasDisagreement) {{
            warningHtml = `<div class="consensus-warning">
                &#9888; Disagreement detected — one or more agents challenge while others support this proposal
            </div>`;
        }}

        proposalsHtml += `<div class="consensus-proposal">
            <div class="consensus-proposal-id">${{proposalId}}</div>
            <div class="consensus-votes">${{votesHtml}}</div>
            ${{warningHtml}}
        </div>`;
    }}

    return `<div class="consensus-panel">
        <div class="consensus-header">
            <h4>Agent Consensus</h4>
            <a class="consensus-link" onclick="switchTab('debate')">View Full Debate &rarr;</a>
        </div>
        ${{proposalsHtml}}
    </div>`;
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
                <button class="btn btn-accept" data-accept-id="${{id}}" onclick="acceptOrder('${{id}}')">Accept &amp; Execute</button>
                <button class="btn btn-deny" data-deny-id="${{id}}" onclick="denyOrder('${{id}}')">Deny</button>
            </div>
        </div>`;
    }}
    panel.innerHTML = html;
}}

// ─── POSITION TABLE STATE ────────────────────────────────────────────────────
let positionSortCol = 'ticker';
let positionSortDir = 'asc';
let positionTickerFilter = '';
let expandedPositions = new Set();
let expandedJournalEntries = new Set();
let positionTableLoading = false;

function sortPositions(col) {{
    if (positionSortCol === col) {{
        positionSortDir = positionSortDir === 'asc' ? 'desc' : 'asc';
    }} else {{
        positionSortCol = col;
        positionSortDir = 'asc';
    }}
    renderPositions();
}}

function filterPositionsByTicker(val) {{
    positionTickerFilter = (val || '').toLowerCase().trim();
    renderPositions();
}}

function togglePositionDetail(ticker) {{
    if (expandedPositions.has(ticker)) {{
        expandedPositions.delete(ticker);
    }} else {{
        expandedPositions.add(ticker);
    }}
    renderPositions();
}}

function toggleJournalDetail(id) {{
    if (expandedJournalEntries.has(id)) {{
        expandedJournalEntries.delete(id);
    }} else {{
        expandedJournalEntries.add(id);
    }}
    renderJournal();
}}

function getPositionSortValue(p, col) {{
    switch (col) {{
        case 'ticker': return (p.ticker || '').toLowerCase();
        case 'direction': return (p.direction || '').toLowerCase();
        case 'status': return (p.status || '').toLowerCase();
        case 'entry': return p.entry_price || 0;
        case 'current': return p.current_price || 0;
        case 'today': return p.daily_change_pct || 0;
        case 'total': return p.combined_pnl_pct || 0;
        case 'size': return p.size_pct_nav || 0;
        case 'hedge': return (p.hedge_ticker || '');
        case 'confidence': return p.conviction || 0;
        case 'days': {{
            const entryDate = p.entry_date ? new Date(p.entry_date) : null;
            return entryDate ? Math.floor((Date.now() - entryDate.getTime()) / 86400000) : 0;
        }}
        default: return '';
    }}
}}

function renderPositions() {{
    const panel = document.getElementById('panel-positions');
    const allPositions = state.book.positions || [];

    // Loading skeleton
    if (positionTableLoading) {{
        panel.innerHTML = renderPositionTableSkeleton();
        return;
    }}

    // Empty state: no positions at all
    if (!allPositions.length) {{
        panel.innerHTML = `<div class="empty-state">
            <div class="empty-icon">&#9898;</div>
            <div class="empty-text">No active positions</div>
            <div style="font-size:0.82em;color:var(--text-muted);margin-top:8px;">Accept a pending recommendation to open your first trade.</div>
        </div>`;
        return;
    }}

    let html = '';

    // Portfolio P&L chart
    const activeForChart = allPositions.filter(p => p.status === 'active');
    html += renderPortfolioChart(activeForChart);

    // Ticker filter input
    html += `<div class="section-title">Positions</div>`;
    html += `<input class="position-filter-input" type="text" placeholder="Filter by ticker..." value="${{escapeHtml(positionTickerFilter)}}" oninput="filterPositionsByTicker(this.value)" aria-label="Filter positions by ticker" />`;

    // Apply filter
    let positions = allPositions;
    if (positionTickerFilter) {{
        positions = positions.filter(p => (p.ticker || '').toLowerCase().includes(positionTickerFilter));
    }}

    // Apply sort
    positions = [...positions].sort((a, b) => {{
        let aVal = getPositionSortValue(a, positionSortCol);
        let bVal = getPositionSortValue(b, positionSortCol);
        if (typeof aVal === 'string') {{
            const cmp = aVal.localeCompare(bVal);
            return positionSortDir === 'asc' ? cmp : -cmp;
        }}
        const cmp = aVal - bVal;
        return positionSortDir === 'asc' ? cmp : -cmp;
    }});

    // Empty after filter
    if (!positions.length) {{
        html += `<div class="empty-state" style="padding:32px 16px;">
            <div class="empty-icon">&#128269;</div>
            <div class="empty-text">No positions match "${{escapeHtml(positionTickerFilter)}}"</div>
        </div>`;
        panel.innerHTML = html;
        return;
    }}

    // Build sortable header helper
    function sortHeader(label, col, isNum) {{
        const activeClass = positionSortCol === col ? (positionSortDir === 'asc' ? ' sort-asc' : ' sort-desc') : '';
        const numClass = isNum ? ' num-col' : '';
        return `<th class="sortable-header${{activeClass}}${{numClass}}" onclick="sortPositions('${{col}}')">${{label}}<span class="sort-arrow">&#9650;</span></th>`;
    }}

    // Table start
    html += `<div class="position-table-wrapper">`;
    html += `<table class="position-table"><thead><tr>`;
    html += sortHeader('Ticker', 'ticker', false);
    html += sortHeader('Direction', 'direction', false);
    html += sortHeader('Status', 'status', false);
    html += sortHeader('Entry', 'entry', true);
    html += sortHeader('Current', 'current', true);
    html += sortHeader('Today', 'today', true);
    html += sortHeader('Total P&L', 'total', true);
    html += sortHeader('Size', 'size', true);
    html += sortHeader('Hedge', 'hedge', false);
    html += sortHeader('Confidence', 'confidence', true);
    html += sortHeader('Days', 'days', true);
    html += `<th style="text-align:center;">Sparkline</th>`;
    html += `<th>Actions</th>`;
    html += `</tr></thead><tbody>`;

    for (const p of positions) {{
        const ticker = p.ticker || '—';
        const direction = (p.direction || '').toLowerCase();
        const status = (p.status || 'active').toLowerCase();
        const entryPrice = p.entry_price;
        const currentPrice = p.current_price;
        const dailyChg = p.daily_change_pct || 0;
        const cpnl = p.combined_pnl_pct || 0;
        const sizePct = p.size_pct_nav || 0;
        const hedge = p.hedge_ticker || '—';
        const hedgeDir = p.hedge_direction || 'short';
        const conviction = p.conviction || 0;
        const entryDate = p.entry_date ? new Date(p.entry_date) : null;
        const days = entryDate ? Math.floor((Date.now() - entryDate.getTime()) / 86400000) : '—';
        const sparkSvg = renderSparkline(p.price_history || []);
        const isExpanded = expandedPositions.has(ticker);

        // Direction badge
        const dirBadge = `<span class="dir-badge ${{direction}}">${{direction.toUpperCase()}}</span>`;

        // Status badge
        const statusBadge = `<span class="status-badge ${{status}}">${{status.toUpperCase()}}</span>`;

        // Confidence classification
        const convClass = classifyConfidence(conviction);

        // Hedge display
        const hedgeDisplay = hedge !== '—' ? `${{hedge}} <span style="color:var(--text-muted);font-size:0.82em;">(${{hedgeDir}})</span>` : '—';

        html += `<tr class="position-row" onclick="togglePositionDetail('${{ticker}}')" aria-expanded="${{isExpanded}}" title="Click to expand details">`;
        html += `<td style="font-weight:700;">${{ticker}}</td>`;
        html += `<td>${{dirBadge}}</td>`;
        html += `<td>${{statusBadge}}</td>`;
        html += `<td class="num-col">${{entryPrice != null ? '$' + entryPrice.toFixed(2) : '—'}}</td>`;
        html += `<td class="num-col">${{currentPrice != null ? '$' + currentPrice.toFixed(2) : '—'}}</td>`;
        html += `<td class="num-col ${{pnlState(dailyChg)}}" style="font-weight:600;">${{formatPctSigned(dailyChg)}}</td>`;
        html += `<td class="num-col ${{pnlState(cpnl)}}" style="font-weight:700;">${{formatPctSigned(cpnl)}}</td>`;
        html += `<td class="num-col">${{(sizePct * 100).toFixed(1)}}%</td>`;
        html += `<td>${{hedgeDisplay}}</td>`;
        html += `<td class="num-col"><span style="color:var(--${{convClass === 'high' ? 'positive' : convClass === 'medium' ? 'warning' : 'text-muted'}});">${{conviction}}/10</span></td>`;
        html += `<td class="num-col">${{days}}</td>`;
        html += `<td style="text-align:center;width:100px;">${{sparkSvg}}</td>`;
        html += `<td><button class="btn-review" onclick="event.stopPropagation();closePosition('${{ticker}}')" aria-label="Review position for ${{ticker}}">Review Position</button></td>`;
        html += `</tr>`;

        // Expandable detail row
        if (isExpanded) {{
            html += `<tr class="position-detail-row"><td colspan="13">`;
            html += renderPositionDetailPanel(p);
            html += `</td></tr>`;
        }}
    }}

    html += `</tbody></table></div>`;
    panel.innerHTML = html;
}}

function renderPositionDetailPanel(p) {{
    const ticker = p.ticker || '—';

    // Try to find related proposal data from state.debates
    const relatedDebates = (state.debates || []).filter(d => {{
        const pid = d.proposal_id || '';
        return pid.toLowerCase().includes(ticker.toLowerCase());
    }});

    // Extract thesis, votes, hedge info, exit criteria from proposal or position
    let thesis = '';
    let entryRationale = '';
    let exitCriteria = '';
    let riskTriggers = '';

    // If position has a proposalId, try to find matching proposal data
    // Also look at pending items that may have enriched _proposal data
    const matchingPending = (state.pending || []).find(r => r.ticker === ticker);
    if (matchingPending && matchingPending._proposal) {{
        thesis = matchingPending._proposal.thesis_summary || matchingPending._proposal.thesisSummary || '';
        entryRationale = matchingPending._proposal.variant_perception || matchingPending._proposal.variantPerception || '';
        exitCriteria = matchingPending._proposal.catalyst || '';
        const risks = matchingPending._proposal.key_risks || matchingPending._proposal.keyRisks || [];
        riskTriggers = Array.isArray(risks) ? risks.join('; ') : risks;
    }}

    // Fallback: use position fields
    const stopLoss = p.stop_loss_method || p.stopLossMethod || '—';
    const takeProfit = p.take_profit || p.takeProfit || '—';

    // Agent votes from debates
    let votesHtml = '';
    if (relatedDebates.length > 0) {{
        votesHtml = '<div class="pdp-section"><div class="pdp-label">Agent Votes</div><div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:6px;">';
        for (const d of relatedDebates.slice(-5)) {{
            const agentName = (d.agent_id || '').replace(/_/g, ' ').replace(/\\b\\w/g, c => c.toUpperCase());
            const stance = (d.stance || 'neutral').toLowerCase();
            const stanceClass = stance === 'support' ? 'badge-blue' : stance === 'challenge' ? 'badge-negative' : 'badge-neutral';
            votesHtml += `<span class="badge ${{stanceClass}}" style="font-size:0.72em;">${{agentName}}: ${{stance.toUpperCase()}} (${{d.revised_conviction || '—'}}/10)</span>`;
        }}
        votesHtml += '</div></div>';
    }}

    // Hedge details
    const hedgeInfo = p.hedge_ticker ? `${{p.hedge_ticker}} (${{p.hedge_direction || 'short'}}) | Hedge P&L: ${{p.hedge_unrealized_pnl_pct != null ? formatPctSigned(p.hedge_unrealized_pnl_pct) : '—'}}` : 'No hedge';

    let html = `<div class="position-detail-panel">`;
    html += `<div class="pdp-grid">`;

    // Thesis
    html += `<div class="pdp-section"><div class="pdp-label">Investment Thesis</div><div class="pdp-value">${{thesis ? escapeHtml(thesis) : 'Not available'}}</div></div>`;

    // Entry Rationale / Variant Perception
    html += `<div class="pdp-section"><div class="pdp-label">Entry Rationale</div><div class="pdp-value">${{entryRationale ? escapeHtml(entryRationale) : 'Not available'}}</div></div>`;

    // Exit criteria
    html += `<div class="pdp-section"><div class="pdp-label">Exit Criteria</div><div class="pdp-value">Stop: ${{escapeHtml(stopLoss)}} | Take Profit: ${{escapeHtml(takeProfit)}}${{exitCriteria ? ' | Catalyst: ' + escapeHtml(exitCriteria) : ''}}</div></div>`;

    // Hedge details
    html += `<div class="pdp-section"><div class="pdp-label">Hedge Details</div><div class="pdp-value">${{hedgeInfo}}</div></div>`;

    // Risk triggers
    if (riskTriggers) {{
        html += `<div class="pdp-section"><div class="pdp-label">Risk Triggers</div><div class="pdp-value">${{escapeHtml(riskTriggers)}}</div></div>`;
    }}

    html += `</div>`;  // pdp-grid

    // Agent votes
    html += votesHtml;

    html += `</div>`;  // position-detail-panel
    return html;
}}

function renderPositionTableSkeleton() {{
    let html = '<div class="section-title">Positions</div>';
    html += '<div class="position-table-wrapper"><table class="position-table"><thead><tr>';
    const cols = ['Ticker','Direction','Status','Entry','Current','Today','Total P&L','Size','Hedge','Confidence','Days','Sparkline','Actions'];
    for (const col of cols) {{
        html += `<th>${{col}}</th>`;
    }}
    html += '</tr></thead><tbody>';
    for (let i = 0; i < 5; i++) {{
        html += '<tr class="position-skeleton-row">';
        for (let j = 0; j < cols.length; j++) {{
            const w = j === 0 ? '60%' : j === cols.length - 1 ? '70%' : '50%';
            html += `<td><div class="position-skeleton-cell" style="width:${{w}};"></div></td>`;
        }}
        html += '</tr>';
    }}
    html += '</tbody></table></div>';
    return html;
}}

function renderJournal() {{
    const panel = document.getElementById('panel-journal');
    const rawJournal = state.book.trade_journal || [];
    if (!rawJournal.length) {{
        panel.innerHTML = '<div class="empty-state"><div class="empty-icon">&#128214;</div><div class="empty-text">No trade history yet.</div></div>';
        return;
    }}
    // Deduplicate by order_id — keep the first (earliest) occurrence
    const seen = new Set();
    const journal = rawJournal.filter(e => {{
        const o = e.order || {{}};
        const id = o.order_id || o.proposal_id || e.timestamp;
        if (seen.has(id)) return false;
        seen.add(id);
        return true;
    }});
    let html = '<div class="section-title">Trade Journal</div><table class="data-table"><thead><tr><th>Action</th><th>Ticker</th><th>Direction</th><th>Conviction</th><th>Size</th><th>Thesis</th><th>Hedge</th><th>Entry</th><th>P&L</th><th>Timestamp</th></tr></thead><tbody>';
    for (const e of [...journal].reverse()) {{
        const o = e.order || {{}};
        const ticker = o.ticker || e.ticker || '—';
        const dir = o.direction || e.direction || '';
        const hedge = o.hedge_ticker || e.hedge || '—';
        const ep = e.entry_price || o.entry_price;
        const pnl = e.realized_pnl_pct;
        const actionClass = e.action === 'open' ? 'badge-positive' : e.action === 'close' ? 'badge-negative' : 'badge-neutral';
        const entryId = o.order_id || o.proposal_id || e.timestamp || ticker;
        const isExpanded = expandedJournalEntries.has(entryId);

        // Extract order fields
        const conviction = o.conviction != null ? o.conviction : '—';
        const sizePct = o.size_pct_nav != null ? (o.size_pct_nav * 100).toFixed(1) + '%' : '—';
        const thesisFull = o.portfolio_thesis || '';
        const thesisTrunc = thesisFull.length > 40 ? thesisFull.substring(0, 40) + '...' : thesisFull || '—';

        html += `<tr class="position-row" onclick="toggleJournalDetail('${{entryId}}')" aria-expanded="${{isExpanded}}" title="Click to expand details" style="cursor:pointer;">
            <td><span class="badge ${{actionClass}}">${{(e.action||'').toUpperCase()}}</span></td>
            <td style="font-weight:600;">${{ticker}}</td>
            <td>${{dir.toUpperCase()}}</td>
            <td>${{conviction !== '—' ? conviction + '/10' : '—'}}</td>
            <td>${{sizePct}}</td>
            <td style="font-size:0.82em;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${{escapeHtml(thesisFull)}}">${{escapeHtml(thesisTrunc)}}</td>
            <td>${{hedge}}</td>
            <td>${{ep ? '$'+Number(ep).toFixed(2) : '—'}}</td>
            <td class="${{pnlState(pnl)}}">${{pnl != null ? formatPctSigned(pnl) : '—'}}</td>
            <td style="font-size:0.82em;color:var(--text-muted);">${{e.timestamp||'—'}}</td>
        </tr>`;

        // Expandable detail row
        if (isExpanded) {{
            html += `<tr class="position-detail-row"><td colspan="10">`;
            html += renderJournalDetailPanel(o, e);
            html += `</td></tr>`;
        }}
    }}
    html += '</tbody></table>';
    panel.innerHTML = html;
}}

function renderJournalDetailPanel(order, entry) {{
    const thesis = order.portfolio_thesis || '—';
    const rationale = order.pm_rationale || '—';
    const conviction = order.conviction != null ? order.conviction + '/10' : '—';
    const size = order.size_pct_nav != null ? (order.size_pct_nav * 100).toFixed(1) + '% NAV' : '—';
    const stopLoss = order.stop_loss_method || '—';
    const takeProfit = order.take_profit || '—';
    const holdingPeriod = order.expected_holding_period || '—';
    const entryApproach = order.entry_approach || '—';
    const reviewDate = order.review_date || '—';

    let html = `<div class="position-detail-panel">`;
    html += `<div class="pdp-grid">`;

    // Portfolio Thesis
    html += `<div class="pdp-section" style="grid-column:1/-1;"><div class="pdp-label">Investment Thesis</div><div class="pdp-value">${{escapeHtml(thesis)}}</div></div>`;

    // PM Rationale
    html += `<div class="pdp-section" style="grid-column:1/-1;"><div class="pdp-label">PM Rationale</div><div class="pdp-value">${{escapeHtml(rationale)}}</div></div>`;

    // Trade Parameters grid
    html += `<div class="pdp-section"><div class="pdp-label">Conviction</div><div class="pdp-value">${{conviction}}</div></div>`;
    html += `<div class="pdp-section"><div class="pdp-label">Position Size</div><div class="pdp-value">${{size}}</div></div>`;
    html += `<div class="pdp-section"><div class="pdp-label">Stop Loss</div><div class="pdp-value">${{escapeHtml(stopLoss)}}</div></div>`;
    html += `<div class="pdp-section"><div class="pdp-label">Take Profit</div><div class="pdp-value">${{escapeHtml(takeProfit)}}</div></div>`;
    html += `<div class="pdp-section"><div class="pdp-label">Holding Period</div><div class="pdp-value">${{escapeHtml(holdingPeriod)}}</div></div>`;
    html += `<div class="pdp-section"><div class="pdp-label">Entry Approach</div><div class="pdp-value">${{escapeHtml(entryApproach)}}</div></div>`;
    html += `<div class="pdp-section"><div class="pdp-label">Review Date</div><div class="pdp-value">${{escapeHtml(reviewDate)}}</div></div>`;

    html += `</div>`;  // pdp-grid
    html += `</div>`;  // position-detail-panel
    return html;
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
                <div class="tl-stat">NAV: <strong>${{formatCurrency(log.nav)}}</strong></div>
            </div>
        </div>`;
    }}
    html += '</div>';
    panel.innerHTML = html;
}}

// ─── EQUITY CHART (Redesigned SVG with range selector, tooltips, drawdown) ──
let chartRange = 'ALL';
let showDrawdown = false;

function filterHistoryByRange(history, range) {{
    if (!history || history.length === 0) return [];
    if (range === 'ALL') return history;
    const now = new Date();
    let cutoff;
    switch (range) {{
        case '1D': cutoff = new Date(now.getTime() - 1 * 24 * 60 * 60 * 1000); break;
        case '1W': cutoff = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000); break;
        case '1M': cutoff = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000); break;
        case '3M': cutoff = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000); break;
        default: return history;
    }}
    const filtered = history.filter(h => {{
        const d = new Date(h.date || h.timestamp);
        return d >= cutoff;
    }});
    return filtered;
}}

function setChartRange(range) {{
    chartRange = range;
    // Re-render only the equity chart section
    const chartContainer = document.getElementById('equity-chart-container');
    if (chartContainer) {{
        chartContainer.innerHTML = renderEquityChartInner();
    }}
    // Update active button
    document.querySelectorAll('.chart-range-btn').forEach(b => {{
        b.classList.toggle('active', b.dataset.range === range);
    }});
}}

function toggleDrawdown() {{
    showDrawdown = !showDrawdown;
    const chartContainer = document.getElementById('equity-chart-container');
    if (chartContainer) {{
        chartContainer.innerHTML = renderEquityChartInner();
    }}
}}

function renderEquityChart() {{
    // Loading state: if state is being loaded for the first time
    if (state.history === undefined) {{
        return `<div class="equity-chart"><div class="chart-skeleton" aria-label="Loading chart"></div></div>`;
    }}

    // Error state: if history is explicitly null (fetch error)
    if (state.history === null) {{
        return `<div class="equity-chart">
            <div class="chart-error-state">
                <div class="cer-icon">&#9888;</div>
                <div class="cer-text">Chart unavailable</div>
            </div>
        </div>`;
    }}

    // Range selector bar
    const ranges = ['1D', '1W', '1M', '3M', 'ALL'];
    let rangeBtns = '<div class="chart-range-bar">';
    for (const r of ranges) {{
        const activeClass = r === chartRange ? ' active' : '';
        rangeBtns += `<button class="chart-range-btn${{activeClass}}" data-range="${{r}}" onclick="setChartRange('${{r}}')" aria-label="Show ${{r}} range">${{r}}</button>`;
    }}
    rangeBtns += `<label class="chart-drawdown-toggle"><input type="checkbox" ${{showDrawdown ? 'checked' : ''}} onchange="toggleDrawdown()"> Drawdown</label>`;
    rangeBtns += '</div>';

    return `<div class="equity-chart">
        ${{rangeBtns}}
        <div id="equity-chart-container">${{renderEquityChartInner()}}</div>
    </div>`;
}}

function renderEquityChartInner() {{
    const history = filterHistoryByRange(state.history, chartRange);

    // Empty state: insufficient data (fewer than 2 points)
    if (!history || history.length === 0) {{
        return `<div class="chart-empty-state">
            <div class="ces-icon">&#128200;</div>
            <div class="ces-text">Insufficient data — mark positions daily to build history</div>
        </div>`;
    }}

    // Single data point: show as a dot with label, not a line
    if (history.length === 1) {{
        const pt = history[0];
        const nav = pt.nav || 10000000;
        const dateStr = formatChartDate(pt.date || pt.timestamp || '');
        const returnPct = pt.totalPnlPct != null ? formatPctSigned(pt.totalPnlPct) : formatPctSigned((nav - 10000000) / 10000000);
        return `<svg viewBox="0 0 800 180" preserveAspectRatio="xMidYMid meet" style="width:100%;height:180px;" role="img" aria-label="Equity chart with single data point">
            <circle cx="400" cy="90" r="6" fill="var(--brand-gold)" />
            <text x="400" y="75" fill="var(--text-primary)" font-size="13" font-weight="700" text-anchor="middle">${{formatDollar(nav)}}</text>
            <text x="400" y="115" fill="var(--text-muted)" font-size="11" text-anchor="middle">${{dateStr}} | ${{returnPct}}</text>
        </svg>`;
    }}

    // Full chart rendering
    const W = 800, H = 180, PAD_L = 60, PAD_R = 20, PAD_T = 16, PAD_B = 30;
    const chartW = W - PAD_L - PAD_R;
    const chartH = H - PAD_T - PAD_B;

    const navs = history.map(h => h.nav || 10000000);
    const initialCapital = state.book.initial_nav || 10000000;

    // Include initial capital in min/max calculation so the reference line is always visible
    const allValues = [...navs, initialCapital];
    const minNav = Math.min(...allValues) * 0.998;
    const maxNav = Math.max(...allValues) * 1.002;
    const rangeNav = maxNav - minNav || 1;

    const scaleX = (i) => PAD_L + (i / (navs.length - 1)) * chartW;
    const scaleY = (v) => PAD_T + chartH - ((v - minNav) / rangeNav) * chartH;

    // Line path
    let pathD = `M ${{scaleX(0)}} ${{scaleY(navs[0])}}`;
    for (let i = 1; i < navs.length; i++) {{
        pathD += ` L ${{scaleX(i)}} ${{scaleY(navs[i])}}`;
    }}

    // Area fill
    const baseY = PAD_T + chartH;
    const areaD = pathD + ` L ${{scaleX(navs.length-1)}} ${{baseY}} L ${{scaleX(0)}} ${{baseY}} Z`;

    // Color based on performance
    const lastNav = navs[navs.length - 1];
    const firstNav = navs[0];
    const lineColor = lastNav > firstNav ? 'var(--positive)' : lastNav < firstNav ? 'var(--negative)' : 'var(--text-muted)';
    const fillColor = lastNav > firstNav ? 'rgba(0,200,83,0.08)' : lastNav < firstNav ? 'rgba(255,23,68,0.08)' : 'rgba(160,160,160,0.05)';

    // Initial capital reference line ($10M horizontal dashed)
    const refY = scaleY(initialCapital);
    const refLine = `<line x1="${{PAD_L}}" y1="${{refY}}" x2="${{W-PAD_R}}" y2="${{refY}}" stroke="var(--brand-gold-dim)" stroke-width="1" stroke-dasharray="5,4" opacity="0.7"/>
    <text x="${{W-PAD_R+2}}" y="${{refY-4}}" fill="var(--brand-gold-dim)" font-size="9" text-anchor="start">$10M</text>`;

    // Tooltip points (circle elements with title attributes for native hover tooltips)
    let points = '';
    const step = Math.max(1, Math.floor(navs.length / 30));  // Limit to ~30 points for performance
    for (let i = 0; i < navs.length; i += step) {{
        const pt = history[i];
        const dateStr = formatChartDate(pt.date || pt.timestamp || '');
        const returnPct = pt.totalPnlPct != null ? formatPctSigned(pt.totalPnlPct) : formatPctSigned((navs[i] - initialCapital) / initialCapital);
        const tooltipText = `${{dateStr}} | NAV: ${{formatDollar(navs[i])}} | Return: ${{returnPct}}`;
        points += `<circle cx="${{scaleX(i)}}" cy="${{scaleY(navs[i])}}" r="3" fill="${{lineColor}}" opacity="0" style="cursor:pointer;"><title>${{tooltipText}}</title></circle>`;
        points += `<circle cx="${{scaleX(i)}}" cy="${{scaleY(navs[i])}}" r="8" fill="transparent" style="cursor:pointer;"><title>${{tooltipText}}</title></circle>`;
    }}
    // Always include last point
    if ((navs.length - 1) % step !== 0) {{
        const i = navs.length - 1;
        const pt = history[i];
        const dateStr = formatChartDate(pt.date || pt.timestamp || '');
        const returnPct = pt.totalPnlPct != null ? formatPctSigned(pt.totalPnlPct) : formatPctSigned((navs[i] - initialCapital) / initialCapital);
        const tooltipText = `${{dateStr}} | NAV: ${{formatDollar(navs[i])}} | Return: ${{returnPct}}`;
        points += `<circle cx="${{scaleX(i)}}" cy="${{scaleY(navs[i])}}" r="4" fill="${{lineColor}}"><title>${{tooltipText}}</title></circle>`;
    }}

    // X-axis labels (more readable date format)
    let xLabels = '';
    const xLabelCount = Math.min(5, navs.length);
    for (let j = 0; j < xLabelCount; j++) {{
        const idx = Math.round(j * (navs.length - 1) / (xLabelCount - 1));
        const dateStr = formatChartDate(history[idx].date || history[idx].timestamp || '');
        const x = scaleX(idx);
        xLabels += `<text x="${{x}}" y="${{H - 4}}" fill="var(--text-muted)" font-size="9.5" text-anchor="middle">${{dateStr}}</text>`;
    }}

    // Y-axis labels (dollar amounts with $)
    const ySteps = 4;
    let yLabels = '';
    for (let j = 0; j <= ySteps; j++) {{
        const val = minNav + (j / ySteps) * rangeNav;
        const y = scaleY(val);
        yLabels += `<text x="${{PAD_L - 6}}" y="${{y + 4}}" fill="var(--text-muted)" font-size="9.5" text-anchor="end">${{formatDollar(val)}}</text>`;
        // Grid line
        if (j > 0 && j < ySteps) {{
            yLabels += `<line x1="${{PAD_L}}" y1="${{y}}" x2="${{W-PAD_R}}" y2="${{y}}" stroke="var(--border)" stroke-width="0.5" opacity="0.4"/>`;
        }}
    }}

    let svg = `<svg viewBox="0 0 ${{W}} ${{H}}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:180px;" role="img" aria-label="Portfolio equity chart">
        <!-- Grid and reference -->
        ${{yLabels}}
        ${{refLine}}
        <!-- X axis base -->
        <line x1="${{PAD_L}}" y1="${{baseY}}" x2="${{W-PAD_R}}" y2="${{baseY}}" stroke="var(--border)" stroke-width="1"/>
        <!-- Area fill -->
        <path d="${{areaD}}" fill="${{fillColor}}" />
        <!-- Equity line -->
        <path d="${{pathD}}" fill="none" stroke="${{lineColor}}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        <!-- Tooltip points -->
        ${{points}}
        <!-- X axis labels -->
        ${{xLabels}}
    </svg>`;

    // Drawdown chart (optional toggle)
    if (showDrawdown) {{
        svg += renderDrawdownChart(history, navs);
    }}

    return svg;
}}

function renderDrawdownChart(history, navs) {{
    // Compute drawdown series: % below peak at each point
    const drawdowns = [];
    let peak = navs[0];
    for (let i = 0; i < navs.length; i++) {{
        if (navs[i] > peak) peak = navs[i];
        const dd = peak > 0 ? (navs[i] - peak) / peak : 0;  // negative or zero
        drawdowns.push(dd);
    }}

    const W = 800, H = 100, PAD_L = 60, PAD_R = 20, PAD_T = 10, PAD_B = 24;
    const chartW = W - PAD_L - PAD_R;
    const chartH = H - PAD_T - PAD_B;

    const minDD = Math.min(...drawdowns, -0.001);  // Always show at least 0 to some negative
    const maxDD = 0;
    const rangeDD = maxDD - minDD || 0.001;

    const scaleX = (i) => PAD_L + (i / (drawdowns.length - 1 || 1)) * chartW;
    const scaleY = (v) => PAD_T + chartH - ((v - minDD) / rangeDD) * chartH;

    // Area fill (drawdown is negative, fill from zero line down)
    const zeroY = scaleY(0);
    let areaPath = `M ${{scaleX(0)}} ${{zeroY}}`;
    for (let i = 0; i < drawdowns.length; i++) {{
        areaPath += ` L ${{scaleX(i)}} ${{scaleY(drawdowns[i])}}`;
    }}
    areaPath += ` L ${{scaleX(drawdowns.length-1)}} ${{zeroY}} Z`;

    // Line path
    let linePath = `M ${{scaleX(0)}} ${{scaleY(drawdowns[0])}}`;
    for (let i = 1; i < drawdowns.length; i++) {{
        linePath += ` L ${{scaleX(i)}} ${{scaleY(drawdowns[i])}}`;
    }}

    // Y-axis labels
    let yLabels = `<text x="${{PAD_L-6}}" y="${{zeroY+4}}" fill="var(--text-muted)" font-size="9" text-anchor="end">0%</text>`;
    yLabels += `<text x="${{PAD_L-6}}" y="${{scaleY(minDD)+4}}" fill="var(--text-muted)" font-size="9" text-anchor="end">${{(minDD*100).toFixed(1)}}%</text>`;
    const midDD = minDD / 2;
    yLabels += `<text x="${{PAD_L-6}}" y="${{scaleY(midDD)+4}}" fill="var(--text-muted)" font-size="9" text-anchor="end">${{(midDD*100).toFixed(1)}}%</text>`;

    // X-axis labels
    let xLabels = '';
    const xLabelCount = Math.min(5, drawdowns.length);
    for (let j = 0; j < xLabelCount; j++) {{
        const idx = Math.round(j * (drawdowns.length - 1) / (xLabelCount - 1));
        const dateStr = formatChartDate(history[idx].date || history[idx].timestamp || '');
        xLabels += `<text x="${{scaleX(idx)}}" y="${{H - 4}}" fill="var(--text-muted)" font-size="9" text-anchor="middle">${{dateStr}}</text>`;
    }}

    return `<div class="drawdown-chart">
        <div style="font-size:0.72em; color:var(--text-muted); font-weight:600; text-transform:uppercase; letter-spacing:0.8px; margin-bottom:6px;">Drawdown from Peak</div>
        <svg viewBox="0 0 ${{W}} ${{H}}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:100px;" role="img" aria-label="Portfolio drawdown chart">
            <!-- Zero line -->
            <line x1="${{PAD_L}}" y1="${{zeroY}}" x2="${{W-PAD_R}}" y2="${{zeroY}}" stroke="var(--border)" stroke-width="1"/>
            <!-- Fill -->
            <path d="${{areaPath}}" fill="rgba(255,23,68,0.1)" />
            <!-- Line -->
            <path d="${{linePath}}" fill="none" stroke="var(--negative)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.8"/>
            <!-- Labels -->
            ${{yLabels}}
            ${{xLabels}}
        </svg>
    </div>`;
}}

function formatChartDate(dateStr) {{
    if (!dateStr) return '';
    try {{
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-US', {{ month: 'short', day: 'numeric' }});
    }} catch(e) {{
        return dateStr.slice(0, 10);
    }}
}}

function formatDollar(val) {{
    if (val == null) return '—';
    if (Math.abs(val) >= 1000000) {{
        return '$' + (val / 1000000).toFixed(2) + 'M';
    }} else if (Math.abs(val) >= 1000) {{
        return '$' + (val / 1000).toFixed(0) + 'K';
    }}
    return '$' + val.toFixed(0);
}}

// ─── HELPERS (legacy aliases) ───────────────────────────────────────────────
function formatMoney(v) {{ return formatCurrency(v); }}
function formatPct(v) {{ return formatPctSigned(v); }}
function pnlClass(v) {{ return pnlState(v); }}

// ─── NEW FORMATTING UTILITIES ───────────────────────────────────────────────
function formatCurrency(val, decimals) {{
    if (val == null) return '—';
    const opts = {{ style: 'currency', currency: 'USD', minimumFractionDigits: decimals != null ? decimals : 0, maximumFractionDigits: decimals != null ? decimals : 0 }};
    return new Intl.NumberFormat('en-US', opts).format(val);
}}

function formatPctSigned(val) {{
    if (val == null) return '—';
    const sign = val > 0 ? '+' : '';
    return sign + (val * 100).toFixed(2) + '%';
}}

function pnlState(val) {{
    if (val == null || val === 0) return 'neutral';
    return val > 0 ? 'positive' : 'negative';
}}

function isStale(isoTimestamp, thresholdHours) {{
    if (!isoTimestamp) return false;
    const threshold = thresholdHours != null ? thresholdHours : 24;
    const ts = new Date(isoTimestamp);
    const now = new Date();
    const day = now.getDay();
    // Only flag staleness on weekdays (Mon-Fri: 1-5)
    if (day === 0 || day === 6) return false;
    const diffHours = (now - ts) / (1000 * 60 * 60);
    return diffHours > threshold;
}}

function classifyConfidence(score) {{
    if (score == null) return 'low';
    if (score >= 8) return 'high';
    if (score >= 5) return 'medium';
    return 'low';
}}

function classifyRisk(decision) {{
    if (!decision) return 'warning';
    const d = decision.toLowerCase().trim();
    if (d.includes('approved') || d.includes('approve') || d === 'proceed') return 'approved';
    if (d.includes('breach') || d.includes('reject') || d.includes('denied')) return 'breach';
    return 'warning';
}}

// ─── PORTFOLIO SUMMARY COMPUTATION ──────────────────────────────────────────
function computePortfolioSummary(book, history, pending) {{
    const b = book || {{}};
    const hist = history || [];
    const pend = pending || [];

    const nav = b.nav || b.initial_nav || 10000000;
    const initialNav = b.initial_nav || 10000000;
    const cashPct = b.cash_pct != null ? b.cash_pct : 1.0;
    const cashDollars = nav * cashPct;
    const positions = b.positions || [];

    const activePositions = positions.filter(p => p.status === 'active');
    const activeCount = activePositions.length;
    const pendingCount = pend.length;

    // Total P&L
    const totalPnlDollars = nav - initialNav;
    const totalPnlPct = initialNav !== 0 ? totalPnlDollars / initialNav : 0;

    // Daily P&L: sum of (daily_change_pct * size_pct_nav * initial_nav) for active positions
    let dailyPnlDollars = 0;
    for (const p of activePositions) {{
        const dailyChg = p.daily_change_pct || 0;
        const size = p.size_pct_nav || 0;
        dailyPnlDollars += dailyChg * size * initialNav;
    }}
    const dailyPnlPct = nav !== 0 ? dailyPnlDollars / nav : 0;

    // Gross exposure: sum of absolute size_pct_nav for all active positions
    let grossExposure = 0;
    let longExposure = 0;
    let shortExposure = 0;

    for (const p of activePositions) {{
        const size = Math.abs(p.size_pct_nav || 0);
        grossExposure += size;

        // Determine if position contributes to long or short exposure
        const dir = (p.direction || '').toLowerCase();
        if (dir === 'long') {{
            longExposure += size;
        }} else if (dir === 'short') {{
            shortExposure += size;
        }}

        // Hedges count as short exposure
        if (p.hedge_ticker) {{
            const hedgeDir = (p.hedge_direction || 'short').toLowerCase();
            if (hedgeDir === 'short') {{
                shortExposure += size;
                grossExposure += size;
            }} else {{
                longExposure += size;
                grossExposure += size;
            }}
        }}
    }}

    // Net exposure: long - short
    const netExposure = longExposure - shortExposure;

    // Drawdown: peak NAV from history vs current NAV
    let peakNav = nav;
    for (const h of hist) {{
        if (h.nav != null && h.nav > peakNav) {{
            peakNav = h.nav;
        }}
    }}
    const drawdownPct = peakNav > 0 ? (peakNav - nav) / peakNav : 0;

    // Risk utilization: gross leverage / 3.0 (max allowed leverage)
    const riskUtilization = grossExposure / 3.0;

    return {{
        nav,
        initialNav,
        totalPnlPct,
        totalPnlDollars,
        dailyPnlPct,
        dailyPnlDollars,
        cashPct,
        cashDollars,
        grossExposure,
        netExposure,
        drawdownPct,
        peakNav,
        riskUtilization,
        activePositions: activeCount,
        pendingCount,
    }};
}}

function renderSparkline(history) {{
    if (!history || history.length < 2) return '<span style="color:var(--text-muted);font-size:0.75em;">—</span>';
    const prices = history.map(h => h.price).filter(p => p != null);
    if (prices.length < 2) return '<span style="color:var(--text-muted);font-size:0.75em;">—</span>';

    const W = 90, H = 28, PAD = 2;
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;

    const scaleX = (i) => PAD + (i / (prices.length - 1)) * (W - PAD * 2);
    const scaleY = (v) => H - PAD - ((v - min) / range) * (H - PAD * 2);

    let d = `M ${{scaleX(0)}} ${{scaleY(prices[0])}}`;
    for (let i = 1; i < prices.length; i++) d += ` L ${{scaleX(i)}} ${{scaleY(prices[i])}}`;

    const isUp = prices[prices.length - 1] >= prices[0];
    const color = isUp ? 'var(--positive)' : 'var(--negative)';

    return `<svg viewBox="0 0 ${{W}} ${{H}}" style="width:90px;height:28px;"><path d="${{d}}" fill="none" stroke="${{color}}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}}

function renderPortfolioChart(positions) {{
    // Build a combined daily P&L series from all position histories
    const dateMap = {{}};  // date -> {{ totalPnl, dailyChange }}

    for (const p of positions) {{
        const hist = p.price_history || [];
        const size = p.size_pct_nav || 0;
        for (const h of hist) {{
            if (!dateMap[h.date]) dateMap[h.date] = {{ pnl: 0, daily: 0 }};
            dateMap[h.date].pnl += (h.combined_pnl_pct || 0) * size;
            dateMap[h.date].daily += (h.daily_change_pct || 0) * size;
        }}
    }}

    const dates = Object.keys(dateMap).sort();
    if (dates.length < 1) return '';

    const pnlSeries = dates.map(d => dateMap[d].pnl);
    const dailySeries = dates.map(d => dateMap[d].daily);

    const W = 700, H = 200, PAD_L = 55, PAD_R = 20, PAD_T = 20, PAD_B = 40;
    const chartW = W - PAD_L - PAD_R;
    const chartH = H - PAD_T - PAD_B;

    // For the line chart: cumulative P&L
    const minPnl = Math.min(0, ...pnlSeries);
    const maxPnl = Math.max(0, ...pnlSeries);
    const rangePnl = (maxPnl - minPnl) || 0.001;

    const scaleX = (i) => PAD_L + (i / Math.max(dates.length - 1, 1)) * chartW;
    const scaleY = (v) => PAD_T + chartH - ((v - minPnl) / rangePnl) * chartH;

    // Zero line
    const zeroY = scaleY(0);

    // Line path
    let linePath = `M ${{scaleX(0)}} ${{scaleY(pnlSeries[0])}}`;
    for (let i = 1; i < pnlSeries.length; i++) {{
        linePath += ` L ${{scaleX(i)}} ${{scaleY(pnlSeries[i])}}`;
    }}

    // Area fill under line
    const areaPath = linePath + ` L ${{scaleX(pnlSeries.length-1)}} ${{zeroY}} L ${{scaleX(0)}} ${{zeroY}} Z`;

    // Daily change bars
    const barWidth = Math.max(4, chartW / dates.length - 2);
    let barsHtml = '';
    for (let i = 0; i < dailySeries.length; i++) {{
        const val = dailySeries[i];
        if (val === 0) continue;
        const x = scaleX(i) - barWidth / 2;
        const barH = Math.abs(val / rangePnl) * chartH;
        const y = val >= 0 ? zeroY - barH : zeroY;
        const color = val >= 0 ? 'var(--positive)' : 'var(--negative)';
        barsHtml += `<rect x="${{x}}" y="${{y}}" width="${{barWidth}}" height="${{Math.max(barH, 1)}}" fill="${{color}}" opacity="0.25" rx="1"/>`;
    }}

    // Determine line color
    const lastPnl = pnlSeries[pnlSeries.length - 1];
    const lineColor = lastPnl > 0 ? 'var(--positive)' : lastPnl < 0 ? 'var(--negative)' : 'var(--text-muted)';
    const fillColor = lastPnl > 0 ? 'rgba(0,200,83,0.06)' : lastPnl < 0 ? 'rgba(255,23,68,0.06)' : 'rgba(160,160,160,0.03)';

    // X-axis labels (show first, middle, last)
    let xLabels = '';
    if (dates.length >= 1) xLabels += `<text x="${{PAD_L}}" y="${{H - 8}}" fill="var(--text-muted)" font-size="10">${{dates[0]}}</text>`;
    if (dates.length >= 3) {{
        const mid = Math.floor(dates.length / 2);
        xLabels += `<text x="${{scaleX(mid)}}" y="${{H - 8}}" fill="var(--text-muted)" font-size="10" text-anchor="middle">${{dates[mid]}}</text>`;
    }}
    if (dates.length >= 2) xLabels += `<text x="${{W - PAD_R}}" y="${{H - 8}}" fill="var(--text-muted)" font-size="10" text-anchor="end">${{dates[dates.length-1]}}</text>`;

    // Y-axis labels
    const yLabels = `
        <text x="${{PAD_L - 6}}" y="${{scaleY(maxPnl) + 4}}" fill="var(--text-muted)" font-size="10" text-anchor="end">${{(maxPnl*100).toFixed(2)}}%</text>
        <text x="${{PAD_L - 6}}" y="${{zeroY + 4}}" fill="var(--text-muted)" font-size="10" text-anchor="end">0%</text>
        <text x="${{PAD_L - 6}}" y="${{scaleY(minPnl) + 4}}" fill="var(--text-muted)" font-size="10" text-anchor="end">${{(minPnl*100).toFixed(2)}}%</text>
    `;

    // Current value label
    const currentLabel = `<text x="${{scaleX(pnlSeries.length-1) + 6}}" y="${{scaleY(lastPnl) + 4}}" fill="${{lineColor}}" font-size="11" font-weight="700">${{(lastPnl*100).toFixed(2)}}%</text>`;

    return `
    <div class="section-title">Portfolio P&L</div>
    <div class="equity-chart" style="margin-bottom:24px;">
        <svg viewBox="0 0 ${{W}} ${{H}}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:200px;">
            <!-- Zero line -->
            <line x1="${{PAD_L}}" y1="${{zeroY}}" x2="${{W-PAD_R}}" y2="${{zeroY}}" stroke="var(--border)" stroke-width="1" stroke-dasharray="4,3"/>
            <!-- Daily bars -->
            ${{barsHtml}}
            <!-- Area fill -->
            <path d="${{areaPath}}" fill="${{fillColor}}" />
            <!-- P&L line -->
            <path d="${{linePath}}" fill="none" stroke="${{lineColor}}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <!-- Dot at latest -->
            <circle cx="${{scaleX(pnlSeries.length-1)}}" cy="${{scaleY(lastPnl)}}" r="4" fill="${{lineColor}}"/>
            <!-- Labels -->
            ${{yLabels}}
            ${{xLabels}}
            ${{currentLabel}}
        </svg>
    </div>`;
}}

// ─── CHAT AGENT ─────────────────────────────────────────────────────────────
let chatMessages = [];
let chatInitialized = false;

function renderChat() {{
    const panel = document.getElementById('panel-chat');
    if (chatInitialized) return;  // Don't re-render — preserve conversation
    chatInitialized = true;

    panel.innerHTML = `
        <div class="chat-container">
            <div class="chat-messages" id="chat-messages">
                <div class="chat-msg assistant">Hi — I'm your portfolio assistant. Ask me anything about your positions, P&L, proposals, risk alerts, or how the system works.</div>
            </div>
            <div class="chat-input-row">
                <textarea class="chat-input" id="chat-input" placeholder="Ask about your portfolio..." rows="1" onkeydown="if(event.key==='Enter'&&!event.shiftKey){{event.preventDefault();sendChatMessage();}}"></textarea>
                <button class="chat-send" id="chat-send-btn" onclick="sendChatMessage()">Send</button>
            </div>
        </div>
    `;
}}

async function sendChatMessage() {{
    const input = document.getElementById('chat-input');
    const btn = document.getElementById('chat-send-btn');
    const messagesEl = document.getElementById('chat-messages');
    const message = input.value.trim();

    if (!message) return;

    // Add user message
    messagesEl.innerHTML += `<div class="chat-msg user">${{escapeHtml(message)}}</div>`;
    input.value = '';
    btn.disabled = true;
    btn.textContent = '...';

    // Show typing indicator
    messagesEl.innerHTML += `<div class="chat-typing" id="chat-typing">Thinking...</div>`;
    messagesEl.scrollTop = messagesEl.scrollHeight;

    try {{
        const resp = await fetch('/api/chat', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ message }}),
        }});
        const data = await resp.json();

        // Remove typing indicator
        const typing = document.getElementById('chat-typing');
        if (typing) typing.remove();

        if (data.error) {{
            messagesEl.innerHTML += `<div class="chat-msg assistant" style="color:var(--negative);">Error: ${{escapeHtml(data.error)}}</div>`;
        }} else {{
            // Simple markdown-like formatting
            const formatted = formatChatResponse(data.answer);
            messagesEl.innerHTML += `<div class="chat-msg assistant">${{formatted}}</div>`;
        }}
    }} catch(e) {{
        const typing = document.getElementById('chat-typing');
        if (typing) typing.remove();
        messagesEl.innerHTML += `<div class="chat-msg assistant" style="color:var(--negative);">Connection error — is serve.py running?</div>`;
    }}

    btn.disabled = false;
    btn.textContent = 'Send';
    messagesEl.scrollTop = messagesEl.scrollHeight;
}}

function formatChatResponse(text) {{
    // Basic formatting: bold, code blocks, newlines
    let html = escapeHtml(text);
    // Code blocks
    html = html.replace(/```([\\s\\S]*?)```/g, '<pre><code>$1</code></pre>');
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold
    html = html.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
    // Newlines
    html = html.replace(/\\n/g, '<br>');
    return html;
}}

function escapeHtml(s) {{ if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }}

function updatePendingBadge() {{
    const el = document.getElementById('pending-count');
    const mobEl = document.getElementById('mob-pending-count');
    if (state.pending.length > 0) {{
        if (el) {{ el.style.display = 'inline'; el.textContent = state.pending.length; }}
        if (mobEl) {{ mobEl.style.display = 'flex'; mobEl.textContent = state.pending.length; }}
    }} else {{
        if (el) el.style.display = 'none';
        if (mobEl) mobEl.style.display = 'none';
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
    chat: 'Portfolio Assistant',
}};

function switchTab(tab) {{
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.mobile-nav-item').forEach(n => n.classList.remove('active'));
    document.getElementById('panel-' + tab).classList.add('active');
    // Desktop sidebar
    const desktopNav = document.querySelector(`.sidebar [data-tab="${{tab}}"]`);
    if (desktopNav) desktopNav.classList.add('active');
    // Mobile bottom nav
    const mobileNav = document.querySelector(`.mobile-nav-item[data-tab="${{tab}}"]`);
    if (mobileNav) mobileNav.classList.add('active');
    document.getElementById('page-title').textContent = TITLES[tab] || 'Dashboard';
    // Scroll to top on tab switch (mobile UX)
    window.scrollTo(0, 0);
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

    # Also write index.html for GitHub Pages
    index_path = BASE_DIR / "index.html"
    with open(index_path, "w") as f:
        f.write(html)

    print(f"Dashboard written to: {OUTPUT_PATH}")
    print(f"  Also: {index_path} (for GitHub Pages)")
    print(f"  Size: {len(html):,} bytes")
    print(f"\n  To use interactively, run:  python3 serve.py")
    print(f"  Then open:  http://127.0.0.1:5100/")

    if not args.no_open:
        subprocess.run(["open", str(OUTPUT_PATH)])


if __name__ == "__main__":
    main()
