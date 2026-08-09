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
    <title>Jimothy Capital — Trading System</title>
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

/* TABULAR NUMBERS — enforce uniform digit width across all numeric displays */
td, th, .metric-value, .metric-sub, .kpi-strip-value, .topbar-stat .value,
.num-col, .factor-chip, .pending-param-value, .risk-metric-value,
.tech-score-value { font-variant-numeric: tabular-nums; }

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
    padding:14px; transition:var(--ease); position:relative; overflow:hidden;
}
.metric-card:hover { border-color:var(--brand-gold); box-shadow:0 8px 24px rgba(0,0,0,0.3); }
.metric-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background:linear-gradient(90deg,var(--brand-gold),var(--brand-gold-dim)); opacity:0; transition:var(--ease); }
.metric-card:hover::before { opacity:1; }
.metric-card.clickable { cursor:pointer; }
.metric-card.clickable:hover { border-color:var(--warning); box-shadow:0 8px 24px rgba(255,171,0,0.15); }
.metric-label { font-size:0.75em; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.8px; font-weight:600; }
.metric-value { font-size:1.6em; font-weight:800; margin-top:6px; }
.metric-sub { font-size:0.78em; color:var(--text-secondary); margin-top:4px; }
.trend-indicator { font-size:0.6em; vertical-align:middle; margin-left:4px; }

/* KPI STRIP (dense single-row numeric bar) */
.kpi-strip {
    display:flex; align-items:center; gap:0; margin-bottom:20px;
    background:var(--bg-card); border:1px solid var(--border); border-radius:8px;
    padding:10px 16px; overflow-x:auto; white-space:nowrap;
    font-variant-numeric:tabular-nums;
}
.kpi-strip-item {
    display:inline-flex; align-items:baseline; gap:5px;
    padding:0 12px; border-right:1px solid var(--border);
    font-size:0.82em; line-height:1;
}
.kpi-strip-item:last-child { border-right:none; }
.kpi-strip-item:first-child { padding-left:0; }
.kpi-strip-label {
    font-weight:600; color:var(--text-muted); text-transform:uppercase;
    font-size:0.85em; letter-spacing:0.3px;
}
.kpi-strip-value {
    font-weight:800; color:var(--text-primary); font-size:1.05em;
}
.kpi-strip-value.positive { color:var(--positive); }
.kpi-strip-value.negative { color:var(--negative); }
.kpi-strip-value.brand { color:var(--brand-gold); }
.kpi-strip-value.info { color:var(--info-blue); }

/* KPI STRIP SKELETON */
.kpi-strip-skeleton {
    display:flex; align-items:center; gap:0; margin-bottom:20px;
    background:var(--bg-card); border:1px solid var(--border); border-radius:8px;
    padding:10px 16px;
}
.kpi-strip-skeleton .skel-item {
    display:inline-flex; align-items:center; gap:6px;
    padding:0 12px; border-right:1px solid var(--border);
}
.kpi-strip-skeleton .skel-item:last-child { border-right:none; }
.kpi-strip-skeleton .skel-bar {
    background: linear-gradient(90deg, var(--bg-hover) 25%, var(--border) 50%, var(--bg-hover) 75%);
    background-size: 200% 100%; animation: pulse 1.5s infinite;
    border-radius:4px; height:1em; width:50px;
}

/* KPI STRIP RESPONSIVE */
@media(max-width:1024px) {
    .kpi-strip { flex-wrap:wrap; white-space:normal; }
    .kpi-strip-item { padding:4px 10px; }
}
@media(max-width:768px) {
    .kpi-strip { flex-wrap:wrap; white-space:normal; gap:4px; }
    .kpi-strip-item { padding:4px 8px; font-size:0.76em; border-right:none; }
}

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
    text-transform:uppercase; letter-spacing:1.2px; margin-bottom:10px;
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
.position-table-wrapper { overflow-x:auto; -webkit-overflow-scrolling:touch; border-radius:10px; }
.position-filter-input {
    background:var(--bg-card); border:1px solid var(--border); border-radius:6px;
    padding:6px 12px; font-size:0.82em; color:var(--text-primary); width:200px;
    outline:none; transition:var(--ease); font-family:inherit; margin-bottom:10px;
}
.position-filter-input:focus { border-color:var(--brand-gold); }
.position-filter-input::placeholder { color:var(--text-muted); }

/* SECTOR FILTER DROPDOWN (Recommendations) */
.sector-filter-select {
    background:var(--bg-card); border:1px solid var(--border); border-radius:8px;
    padding:9px 14px; font-size:0.88em; color:var(--text-primary); width:220px;
    outline:none; transition:var(--ease); font-family:inherit; margin-bottom:14px;
    cursor:pointer; appearance:none; -webkit-appearance:none;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%23b0b0b0' viewBox='0 0 16 16'%3E%3Cpath d='M4 6l4 4 4-4'/%3E%3C/svg%3E");
    background-repeat:no-repeat; background-position:right 12px center;
    padding-right:32px;
}
.sector-filter-select:focus { border-color:var(--brand-gold); }
.sector-filter-select option { background:var(--bg-secondary); color:var(--text-primary); }
.sortable-header {
    cursor:pointer; user-select:none; white-space:nowrap; position:relative;
    transition:var(--ease);
}
.sortable-header:hover { color:var(--brand-gold); }
.sortable-header .sort-arrow { display:inline-block; margin-left:4px; font-size:0.7em; opacity:0.5; transition:var(--ease); }
.sortable-header.sort-asc .sort-arrow { opacity:1; color:var(--brand-gold); }
.sortable-header.sort-desc .sort-arrow { opacity:1; color:var(--brand-gold); transform:rotate(180deg); }
.position-table thead th { position:sticky; top:0; z-index:10; }
.position-table { width:100%; border-collapse:separate; border-spacing:0; background:var(--bg-card); border:1px solid var(--border); border-radius:10px; overflow:hidden; }
.position-table thead th { background:var(--bg-secondary); color:var(--text-muted); font-size:0.70em; font-weight:700; text-transform:uppercase; letter-spacing:0.8px; padding:6px 8px; text-align:left; border-bottom:1px solid var(--border); line-height:1.2; }
.position-table thead th.num-col { text-align:right; }
.position-table tbody td { padding:5px 8px; font-size:0.82em; border-bottom:1px solid var(--border); transition:var(--ease); vertical-align:middle; line-height:1.3; font-variant-numeric:tabular-nums; }
.position-table tbody td.num-col { text-align:right; font-variant-numeric:tabular-nums; }
.position-table tbody tr:last-child td { border-bottom:none; }
.position-table tbody tr.position-row { cursor:pointer; }
.position-table tbody tr.position-row:hover td { background:var(--bg-hover); }
.position-table tbody tr.position-detail-row td { background:var(--bg-primary); padding:0; border-bottom:1px solid var(--border); }
.position-detail-panel {
    padding:12px 14px; font-size:0.82em; color:var(--text-secondary); line-height:1.4;
    animation:fadeIn 0.2s ease;
}
.position-detail-panel .pdp-section { margin-bottom:10px; }
.position-detail-panel .pdp-section:last-child { margin-bottom:0; }
.position-detail-panel .pdp-label { font-weight:700; color:var(--text-primary); font-size:0.85em; text-transform:uppercase; letter-spacing:0.4px; margin-bottom:3px; }
.position-detail-panel .pdp-value { color:var(--text-secondary); }
.position-detail-panel .pdp-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; }

/* JOURNAL DATE GROUP HEADERS */
.journal-group-header td { padding:18px 16px 8px 16px; font-size:0.82em; font-weight:700; text-transform:uppercase; letter-spacing:0.8px; color:var(--text-muted); border-bottom:1px solid var(--border); border-top:2px solid var(--border); background:transparent; }
.data-table tbody tr.journal-group-header:first-child td { border-top:none; }
.data-table tbody tr.journal-group-header:hover td { background:transparent; }

/* Direction & Status Badges (position table) */
.dir-badge { display:inline-flex; align-items:center; padding:3px 10px; border-radius:14px; font-size:0.75em; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; }
.dir-badge.long { background:rgba(0,200,83,0.12); color:var(--positive); }
.dir-badge.short { background:rgba(255,23,68,0.12); color:var(--negative); }
.status-badge { display:inline-flex; align-items:center; padding:3px 10px; border-radius:14px; font-size:0.72em; font-weight:700; text-transform:uppercase; letter-spacing:0.4px; }
.status-badge.active { background:rgba(0,200,83,0.12); color:var(--positive); }
.status-badge.closed { background:rgba(160,160,160,0.1); color:var(--text-secondary); }
.status-badge.stopped { background:rgba(255,23,68,0.12); color:var(--negative); }

/* Position table skeleton */
.position-skeleton-row td { padding:5px 8px !important; }
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
    padding:18px; margin-bottom:16px; position:relative; overflow:hidden;
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

/* SECTOR EXPOSURE TABLE */
.sector-table-wrapper { overflow-x:auto; -webkit-overflow-scrolling:touch; border-radius:10px; margin-bottom:20px; }
.sector-table { width:100%; border-collapse:separate; border-spacing:0; background:var(--bg-card); border:1px solid var(--border); border-radius:10px; overflow:hidden; font-variant-numeric:tabular-nums; min-width:400px; }
.sector-table thead th { background:var(--bg-secondary); color:var(--text-muted); font-size:0.70em; font-weight:700; text-transform:uppercase; letter-spacing:0.8px; padding:10px 14px; text-align:left; border-bottom:1px solid var(--border); }
.sector-table thead th.num-col { text-align:right; }
.sector-table tbody td { padding:8px 14px; font-size:0.84em; border-bottom:1px solid var(--border); }
.sector-table tbody td.num-col { text-align:right; font-weight:600; }
.sector-table tbody tr:last-child td { border-bottom:none; }
.sector-table tbody tr:hover td { background:var(--bg-hover); }

/* FACTOR BETA CHIPS */
.factor-chips-row {
    display:flex; flex-wrap:wrap; gap:8px; margin-bottom:20px;
    align-items:center;
}
.factor-chip {
    display:inline-flex; align-items:center; gap:5px;
    padding:5px 12px; border-radius:16px;
    font-size:0.78em; font-weight:600; font-variant-numeric:tabular-nums;
    border:1px solid transparent;
    white-space:nowrap;
}
.factor-chip.chip-green { background:rgba(0,200,83,0.12); color:var(--positive); border-color:rgba(0,200,83,0.25); }
.factor-chip.chip-amber { background:rgba(255,171,0,0.12); color:var(--warning); border-color:rgba(255,171,0,0.25); }
.factor-chip.chip-red { background:rgba(255,23,68,0.12); color:var(--negative); border-color:rgba(255,23,68,0.25); }
@media(max-width:768px) {
    .factor-chips-row { gap:6px; }
    .factor-chip { font-size:0.72em; padding:4px 10px; }
}

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
    .sector-table-wrapper { margin-bottom:16px; }
    .sector-table { min-width:360px; }
    .sector-table thead th { padding:8px 10px; font-size:0.66em; }
    .sector-table tbody td { padding:6px 10px; font-size:0.78em; }
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
        <h1>Jimothy Capital</h1>
        <div class="sub">Systematic L/S Equity</div>
    </div>
    <div class="sidebar-nav">
        <div class="nav-label">Dashboard</div>
        <div class="nav-item active" data-tab="overview" onclick="switchTab('overview')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('overview');}">Overview</div>
        <div class="nav-item" data-tab="pending" onclick="switchTab('pending')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('pending');}">
            Recommendations <span class="badge-count" id="pending-count" style="display:none;">0</span>
        </div>
        <div class="nav-item" data-tab="positions" onclick="switchTab('positions')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('positions');}">Book</div>
        <div class="nav-item" data-tab="journal" onclick="switchTab('journal')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('journal');}">Blotter</div>

        <div class="nav-label">Analysis</div>
        <div class="nav-item" data-tab="debate" onclick="switchTab('debate')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('debate');}">IC Debate</div>
        <div class="nav-item" data-tab="risk" onclick="switchTab('risk')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('risk');}">Risk</div>
        <div class="nav-item" data-tab="technical" onclick="switchTab('technical')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('technical');}">Technicals</div>
        <div class="nav-item" data-tab="calendar" onclick="switchTab('calendar')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('calendar');}">Calendar</div>

        <div class="nav-label">History</div>
        <div class="nav-item" data-tab="timeline" onclick="switchTab('timeline')" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();switchTab('timeline');}">Run Log</div>

        <div class="nav-label">Desk</div>
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
        <div class="topbar-left"><h2 id="page-title">Jimothy Paper Trading LLC</h2></div>
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
        <div class="panel" id="panel-calendar"></div>
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
    derived: null,
    calendar: null,
    factors: null,
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

    // Fetch calendar and factors data
    const [calendarData, factorsData] = await Promise.all([
        apiFetch('/api/calendar'),
        apiFetch('/api/factors'),
    ]);
    if (calendarData) state.calendar = calendarData;
    if (factorsData) state.factors = factorsData;

    // Compute derived metrics from raw state
    state.derived = computeDerivedMetrics(state);

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
    renderCalendar();
    renderTimeline();
    renderChat();
    updatePendingBadge();
}}

function renderDashboardHeader() {{
    const container = document.getElementById('dashboard-header');
    if (!container) return;

    const lastMarked = state.book.last_marked;
    let lastUpdatedStr = formatTimestampET(lastMarked);
    if (lastUpdatedStr === '—') lastUpdatedStr = 'Never';

    container.innerHTML = `
        <div class="dashboard-header">
            <div class="dashboard-header-top">
                <div class="dashboard-header-title">
                    <h2>Jimothy Paper Trading LLC</h2>
                    <div class="dashboard-header-meta">Last updated: ${{lastUpdatedStr}}</div>
                </div>
                <span class="badge-paper">LIVE — PAPER BOOK</span>
            </div>
            <div class="header-actions">
                <button class="btn-header" id="btn-refresh-data" onclick="handleRefreshData()">
                    Mark to Market
                </button>
                <button class="btn-header" id="btn-run-cycle" onclick="handleRunCycle()">
                    Run IC Sweep
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

async function handleRunCycle() {{
    const btn = document.getElementById('btn-run-cycle');
    if (!btn) return;
    showConfirmModal('Run IC Sweep', 'This will trigger all sector and macro analysts to generate new relative-value trade recommendations. It may take several minutes. Continue?', async function() {{
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Running...';
        const r = await apiPost('/api/run-cycle');
        if (r) {{
            showToast(r.message || 'IC sweep initiated', 'success');
            showCycleOverlay();
            pollCycleStatus();
        }} else {{
            btn.disabled = false;
            btn.innerHTML = 'Run IC Sweep';
        }}
    }}, 'approve');
}}

// ─── CYCLE PROGRESS OVERLAY ──────────────────────────────────────────────────
function showCycleOverlay() {{
    if (document.getElementById('cycle-overlay')) return;
    const overlay = document.createElement('div');
    overlay.id = 'cycle-overlay';
    overlay.innerHTML = `
        <div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.75);z-index:9500;display:flex;align-items:center;justify-content:center;">
            <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:16px;padding:36px 48px;max-width:480px;width:90%;text-align:center;box-shadow:0 16px 48px rgba(0,0,0,0.5);">
                <div style="font-size:1.3em;font-weight:700;color:var(--text-primary);margin-bottom:8px;" id="cycle-phase">Initiating IC sweep...</div>
                <div style="font-size:0.85em;color:var(--text-secondary);margin-bottom:20px;" id="cycle-detail">Screening universe...</div>
                <div style="width:100%;height:8px;background:var(--bg-hover);border-radius:4px;overflow:hidden;margin-bottom:16px;">
                    <div id="cycle-progress-bar" style="height:100%;width:0%;background:linear-gradient(90deg,var(--brand-gold),var(--positive));border-radius:4px;transition:width 0.8s ease;"></div>
                </div>
                <div style="font-size:0.75em;color:var(--text-muted);" id="cycle-pct">0%</div>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
}}

function hideCycleOverlay() {{
    const overlay = document.getElementById('cycle-overlay');
    if (overlay) overlay.remove();
    const btn = document.getElementById('btn-run-cycle');
    if (btn) {{ btn.disabled = false; btn.innerHTML = 'Run IC Sweep'; }}
}}

let cyclePolling = null;
function pollCycleStatus() {{
    if (cyclePolling) clearInterval(cyclePolling);
    cyclePolling = setInterval(async () => {{
        const data = await apiFetch('/api/cycle-status');
        if (!data) return;

        const phaseEl = document.getElementById('cycle-phase');
        const detailEl = document.getElementById('cycle-detail');
        const barEl = document.getElementById('cycle-progress-bar');
        const pctEl = document.getElementById('cycle-pct');

        if (phaseEl) phaseEl.textContent = data.phase || 'Working...';
        if (detailEl) detailEl.textContent = data.detail || '';
        if (barEl) barEl.style.width = (data.progress || 0) + '%';
        if (pctEl) pctEl.textContent = (data.progress || 0) + '%';

        if (!data.running) {{
            clearInterval(cyclePolling);
            cyclePolling = null;
            if (data.progress === 100) {{
                showToast('IC sweep complete — review recommendations', 'success');
            }} else if (data.phase && data.phase.startsWith('Error')) {{
                showToast('IC sweep failed: ' + data.phase, 'error');
            }}
            setTimeout(() => {{
                hideCycleOverlay();
                refreshAll();
            }}, 1500);
        }}
    }}, 3000);
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
    const etNow = new Date(now.toLocaleString('en-US', {{ timeZone: 'America/New_York' }}));
    const hh = etNow.getHours().toString().padStart(2, '0');
    const mm = etNow.getMinutes().toString().padStart(2, '0');
    if (statusEl) {{
        statusEl.textContent = 'Last: ' + hh + ':' + mm + ' ET';
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
            refreshTimeStr = formatTimestampET(lastMarked);
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
            lastCycleStr = formatTimestampET(ts);
            if (lastCycleStr === '—') lastCycleStr = 'Unknown';
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

    // Leverage regime badge (Task 6.1)
    const leverageRegime = state.book.leverage_regime || null;
    const regimeText = leverageRegime ? leverageRegime.toUpperCase() : '—';
    const regimeCol = regimeColor(leverageRegime);
    const regimeBgMap = {{ 'green': 'rgba(0,200,83,0.12)', 'red': 'rgba(255,23,68,0.12)', 'gray': 'rgba(160,160,160,0.1)' }};
    const regimeColorMap = {{ 'green': 'var(--positive)', 'red': 'var(--negative)', 'gray': 'var(--text-secondary)' }};
    const regimeBg = regimeBgMap[regimeCol] || regimeBgMap['gray'];
    const regimeFg = regimeColorMap[regimeCol] || regimeColorMap['gray'];

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
        <div class="shp-item">
            <span class="shp-label">Regime</span>
            <span style="display:inline-flex;align-items:center;padding:3px 10px;border-radius:12px;font-size:0.78em;font-weight:700;background:${{regimeBg}};color:${{regimeFg}};">${{regimeText}}</span>
        </div>
        ${{staleWarningHtml}}
    </div>`;
}}

// ─── KPI STRIP (dense single-row numeric bar) ───────────────────────────────
function renderKPIStrip() {{
    const summary = computePortfolioSummary(state.book, state.history, state.pending);
    if (!summary) return renderKPIStripSkeleton();

    // Compute long/short counts from active positions
    const positions = (state.book.positions || []).filter(p => p.status === 'active');
    let longCount = 0;
    let shortCount = 0;
    for (const p of positions) {{
        const dir = (p.direction || '').toLowerCase();
        if (dir === 'long') longCount++;
        else if (dir === 'short') shortCount++;
    }}

    // Daily P&L in bps (relative to NAV)
    const dayBps = Math.round(summary.dailyPnlPct * 10000);
    // MTD / YTD — use totalPnlPct as best available proxy (MTD/YTD separate data not always available)
    const mtdBps = state.derived && state.derived.mtdPnlBps != null ? state.derived.mtdPnlBps : Math.round(summary.totalPnlPct * 10000);
    const ytdBps = state.derived && state.derived.ytdPnlBps != null ? state.derived.ytdPnlBps : Math.round(summary.totalPnlPct * 10000);
    // Drawdown in bps from HWM
    const ddBps = -Math.round(summary.drawdownPct * 10000);
    // Gross/Net as percentage
    const grossPct = (summary.grossExposure * 100).toFixed(0);
    const netPct = (summary.netExposure >= 0 ? '+' : '') + (summary.netExposure * 100).toFixed(0);

    // Format NAV compactly (e.g. $10.0M, $650M)
    function fmtNav(val) {{
        if (val >= 1e9) return '$' + (val / 1e9).toFixed(1) + 'B';
        if (val >= 1e6) return '$' + (val / 1e6).toFixed(0) + 'M';
        if (val >= 1e3) return '$' + (val / 1e3).toFixed(0) + 'K';
        return '$' + val.toFixed(0);
    }}

    function bpsClass(v) {{ return v > 0 ? 'positive' : v < 0 ? 'negative' : ''; }}

    const items = [
        {{ label: 'NAV', value: fmtNav(summary.nav), cls: 'brand' }},
        {{ label: 'Day', value: (dayBps >= 0 ? '+' : '') + dayBps + 'bps', cls: bpsClass(dayBps) }},
        {{ label: 'MTD', value: (mtdBps >= 0 ? '+' : '') + mtdBps + 'bps', cls: bpsClass(mtdBps) }},
        {{ label: 'YTD', value: (ytdBps >= 0 ? '+' : '') + ytdBps + 'bps', cls: bpsClass(ytdBps) }},
        {{ label: 'Gross', value: grossPct + '%', cls: '' }},
        {{ label: 'Net', value: netPct + '%', cls: 'info' }},
        {{ label: 'Long', value: String(longCount), cls: '' }},
        {{ label: 'Short', value: String(shortCount), cls: '' }},
        {{ label: 'DD', value: (ddBps <= 0 ? '' : '+') + ddBps + 'bps', cls: ddBps < 0 ? 'negative' : '' }},
    ];

    let html = '<div class="kpi-strip" role="region" aria-label="Portfolio KPI Strip">';
    for (const item of items) {{
        const valCls = item.cls ? ' ' + item.cls : '';
        html += `<div class="kpi-strip-item"><span class="kpi-strip-label">${{item.label}}:</span><span class="kpi-strip-value${{valCls}}">${{item.value}}</span></div>`;
    }}
    html += '</div>';
    return html;
}}

function renderKPIStripSkeleton() {{
    const labels = ['NAV','Day','MTD','YTD','Gross','Net','Long','Short','DD'];
    let html = '<div class="kpi-strip-skeleton">';
    for (const label of labels) {{
        html += `<div class="skel-item"><span style="font-size:0.75em;color:var(--text-muted);font-weight:600;text-transform:uppercase;">${{label}}:</span><span class="skel-bar"></span></div>`;
    }}
    html += '</div>';
    return html;
}}

// ─── SECTOR EXPOSURE TABLE ───────────────────────────────────────────────────
function renderSectorExposure() {{
    const positions = (state.book.positions || []).filter(p => p.status === 'active');
    if (positions.length === 0) return '';

    // Group by sector
    const sectors = {{}};
    for (const p of positions) {{
        const sector = p.sector || HEDGE_TO_SECTOR[p.hedge_ticker] || 'Unknown';
        if (!sectors[sector]) sectors[sector] = {{ netPct: 0, names: 0, dayPnl: 0 }};
        const size = p.size_pct_nav || 0;
        const dir = (p.direction || 'long').toLowerCase();
        const signedSize = dir === 'long' ? size : -size;
        sectors[sector].netPct += signedSize;
        sectors[sector].names += 1;
        // Daily P&L contribution in bps: daily_change_pct * size_pct_nav * 10000
        const dailyChg = p.daily_change_pct || 0;
        sectors[sector].dayPnl += dailyChg * size * 10000;
    }}

    const sectorEntries = Object.entries(sectors).sort((a, b) => Math.abs(b[1].netPct) - Math.abs(a[1].netPct));
    if (sectorEntries.length === 0) return '';

    let html = `<div class="sector-table-wrapper"><table class="sector-table" role="table" aria-label="Sector Exposure">`;
    html += `<thead><tr><th>Sector</th><th class="num-col">Net %</th><th class="num-col"># Names</th><th class="num-col">Day P&L</th></tr></thead>`;
    html += `<tbody>`;

    for (const [sector, data] of sectorEntries) {{
        const netPctStr = (data.netPct >= 0 ? '+' : '') + (data.netPct * 100).toFixed(1) + '%';
        const netCls = data.netPct > 0 ? 'positive' : data.netPct < 0 ? 'negative' : '';
        const dayPnlBps = Math.round(data.dayPnl);
        const dayPnlStr = (dayPnlBps >= 0 ? '+' : '') + dayPnlBps + 'bps';
        const dayPnlCls = dayPnlBps > 0 ? 'positive' : dayPnlBps < 0 ? 'negative' : '';

        html += `<tr>`;
        html += `<td style="font-weight:600;">${{sector}}</td>`;
        html += `<td class="num-col ${{netCls}}">${{netPctStr}}</td>`;
        html += `<td class="num-col">${{data.names}}</td>`;
        html += `<td class="num-col ${{dayPnlCls}}">${{dayPnlStr}}</td>`;
        html += `</tr>`;
    }}

    html += `</tbody></table></div>`;
    return html;
}}

// ─── FACTOR BETA CHIPS ───────────────────────────────────────────────────────
function renderFactorBetaChips() {{
    // Factor display config: key -> short label
    const CHIP_FACTORS = [
        {{ key: 'USD_DXY', label: 'DXY' }},
        {{ key: 'SPX', label: 'SPX' }},
        {{ key: 'RATES_10Y', label: '10Y' }},
        {{ key: 'VIX', label: 'VIX' }},
        {{ key: 'CRUDE_CL1', label: 'CL1' }},
        {{ key: 'GROWTH_VALUE', label: 'Grw/Val' }},
    ];

    // Source factor data from state.factors (API /api/factors)
    const factorData = (state.factors && state.factors.available) ? state.factors.factors : null;
    if (!factorData) {{
        // Render placeholder chips with dashes when no data available
        let html = '<div class="factor-chips-row" role="region" aria-label="Factor Betas">';
        for (const f of CHIP_FACTORS) {{
            html += `<span class="factor-chip chip-green">${{f.label}} —</span>`;
        }}
        html += '</div>';
        return html;
    }}

    // Thresholds: |beta| > 0.10 = red (breach), > 0.05 = amber (warning), else green
    function chipClass(beta) {{
        if (beta == null) return 'chip-green';
        const abs = Math.abs(beta);
        if (abs > 0.10) return 'chip-red';
        if (abs > 0.05) return 'chip-amber';
        return 'chip-green';
    }}

    let html = '<div class="factor-chips-row" role="region" aria-label="Factor Betas">';
    for (const f of CHIP_FACTORS) {{
        const beta = factorData[f.key];
        const betaStr = beta != null ? ((beta >= 0 ? '+' : '') + beta.toFixed(2)) : '—';
        const cls = chipClass(beta);
        html += `<span class="factor-chip ${{cls}}">${{f.label}} ${{betaStr}}</span>`;
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

    let html = renderKPIStrip();

    // Sector Exposure Table (compact, one row per active sector)
    html += renderSectorExposure();

    // Factor Beta Chips (single row of colored chips below sector table)
    html += renderFactorBetaChips();

    // Factor warnings + Total Loss-at-Trail KPI (Task 6.2)
    let factorWarningsHtml = '';
    if (state.factors && state.factors.available) {{
        const FACTOR_DISPLAY = {{
            'USD_DXY': 'USD/DXY', 'SPX': 'SPX', 'RATES_10Y': '10Y',
            'VIX': 'VIX', 'GROWTH_VALUE': 'Grw/Val', 'CRUDE_CL1': 'Crude',
            'LARGE_SMALL': 'Lg/Sm', 'HY_CREDIT': 'HY', 'GOLD_XAU': 'Gold'
        }};
        const warningFactors = Object.entries(state.factors.factors || {{}}).filter(([k, v]) => Math.abs(v) > 0.4);
        if (warningFactors.length > 0) {{
            factorWarningsHtml = `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:14px 18px;margin-bottom:16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
                <span style="font-size:0.75em;font-weight:700;color:var(--warning);text-transform:uppercase;letter-spacing:0.5px;">&#9888; Factor Warning</span>`;
            for (const [key, val] of warningFactors) {{
                const cls = Math.abs(val) > 0.6 ? 'badge-negative' : 'badge-warning';
                factorWarningsHtml += `<span class="badge ${{cls}}" style="font-size:0.75em;">${{FACTOR_DISPLAY[key] || key}}: ${{val > 0 ? '+' : ''}}${{val.toFixed(2)}}</span>`;
            }}
            factorWarningsHtml += `</div>`;
        }}
    }}
    html += factorWarningsHtml;

    // Total Loss-at-Trail KPI (Task 6.2)
    if (state.derived) {{
        const totalLAT = state.derived.totalLossAtTrail;
        html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:14px 18px;margin-bottom:16px;display:flex;align-items:center;gap:16px;">
            <div>
                <div style="font-size:0.72em;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.8px;">Total Loss-at-Trail</div>
                <div style="font-size:1.4em;font-weight:800;color:var(--negative);margin-top:4px;">${{totalLAT}} bps</div>
            </div>
            <div style="font-size:0.78em;color:var(--text-muted);margin-left:auto;">Max portfolio impact if all trails trigger simultaneously</div>
        </div>`;
    }}

    // Action Required panel removed — recommendations have their own dedicated tab (Task 1)

    // Agent Consensus removed from overview — IC Debate tab covers this (Task 1)

    // Equity curve removed from overview — moved to Book tab (Task 3)

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

    // Compact Calendar Widget (Task 6.3)
    html += renderCalendarCompact();

    document.getElementById('panel-overview').innerHTML = html;
}}

// ─── COMPACT CALENDAR WIDGET (Task 6.3) ─────────────────────────────────────
function renderCalendarCompact() {{
    if (!state.calendar || state.calendar.empty) {{
        return `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:18px 20px;margin-top:20px;">
            <div style="font-size:0.78em;font-weight:700;color:var(--brand-gold-dim);text-transform:uppercase;letter-spacing:1.2px;margin-bottom:10px;">Week Ahead</div>
            <div style="color:var(--text-muted);font-size:0.88em;">No calendar data available</div>
        </div>`;
    }}

    let items = [];
    const cal = state.calendar;

    // Gather up to 5-6 items across categories
    if (cal.macro && cal.macro.length) {{
        for (const e of cal.macro.slice(0, 2)) {{
            items.push(`<div style="display:flex;align-items:center;gap:8px;padding:5px 0;"><span style="font-size:0.7em;font-weight:700;color:var(--steel-blue);text-transform:uppercase;min-width:40px;">MACRO</span><span style="font-size:0.84em;color:var(--text-secondary);">${{escapeHtml(e.day || e.date || '')}} ${{escapeHtml(e.time || '')}} — ${{escapeHtml(e.release || e.event || '')}}</span><span style="font-size:0.75em;color:var(--text-muted);margin-left:auto;">${{escapeHtml(e.currency || '')}}</span></div>`);
        }}
    }}
    if (cal.cb && cal.cb.length) {{
        for (const e of cal.cb.slice(0, 2)) {{
            items.push(`<div style="display:flex;align-items:center;gap:8px;padding:5px 0;"><span style="font-size:0.7em;font-weight:700;color:var(--warning);text-transform:uppercase;min-width:40px;">CB</span><span style="font-size:0.84em;color:var(--text-secondary);">${{escapeHtml(e.date || '')}} — ${{escapeHtml(e.currency || '')}} ${{escapeHtml(e.action || '')}}</span></div>`);
        }}
    }}
    if (cal.earnings && cal.earnings.length) {{
        for (const e of cal.earnings.slice(0, 2)) {{
            items.push(`<div style="display:flex;align-items:center;gap:8px;padding:5px 0;"><span style="font-size:0.7em;font-weight:700;color:var(--positive);text-transform:uppercase;min-width:40px;">EARN</span><span style="font-size:0.84em;color:var(--text-secondary);">${{escapeHtml(e.date || '')}} — ${{escapeHtml(e.ticker || '')}} (${{escapeHtml(e.timing || '')}})</span></div>`);
        }}
    }}

    // Limit to max 6
    items = items.slice(0, 6);

    if (items.length === 0) {{
        return `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:18px 20px;margin-top:20px;">
            <div style="font-size:0.78em;font-weight:700;color:var(--brand-gold-dim);text-transform:uppercase;letter-spacing:1.2px;margin-bottom:10px;">Week Ahead</div>
            <div style="color:var(--text-muted);font-size:0.88em;">No calendar data available</div>
        </div>`;
    }}

    return `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:18px 20px;margin-top:20px;">
        <div style="font-size:0.78em;font-weight:700;color:var(--brand-gold-dim);text-transform:uppercase;letter-spacing:1.2px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between;">
            <span>Week Ahead</span>
            <a style="font-size:1em;color:var(--brand-gold);cursor:pointer;text-decoration:none;font-weight:600;text-transform:none;letter-spacing:0;" onclick="switchTab('calendar')">View All &rarr;</a>
        </div>
        ${{items.join('')}}
    </div>`;
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
        let tsDisplay = formatTimestampET(timestamp);

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
        if (tsDisplay && tsDisplay !== '—') {{
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
let pendingSectorFilter = 'All';

function filterPendingBySector(val) {{
    pendingSectorFilter = val;
    renderPending();
}}

function renderPending() {{
    const panel = document.getElementById('panel-pending');
    if (!state.pending.length) {{
        panel.innerHTML = '<div class="empty-state"><div class="empty-icon">&#10003;</div><div class="empty-text">No pending recommendations. Run an IC sweep to generate new ideas.</div></div>';
        return;
    }}

    // Sort by conviction descending (highest first)
    const sorted = [...state.pending].sort((a, b) => {{
        const ca = Number(a.conviction || (a._proposal && a._proposal.conviction) || 0);
        const cb = Number(b.conviction || (b._proposal && b._proposal.conviction) || 0);
        return cb - ca;
    }});

    // Derive sector for each item using HEDGE_TO_SECTOR mapping
    const getSector = (o) => {{
        const prop = o._proposal || {{}};
        return o.sector || prop.sector || HEDGE_TO_SECTOR[o.hedge_ticker] || 'Unknown';
    }};

    // Collect unique sectors for the dropdown
    const allSectors = [...new Set(sorted.map(o => getSector(o)))].sort();

    // Apply sector filter
    const filtered = pendingSectorFilter === 'All' ? sorted : sorted.filter(o => getSector(o) === pendingSectorFilter);

    // Build header with filter
    let html = '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:14px;">';
    html += '<div class="section-title" style="margin-bottom:0;">Trade Recommendations Awaiting Approval</div>';
    html += `<select class="sector-filter-select" onchange="filterPendingBySector(this.value)" aria-label="Filter by sector">`;
    html += `<option value="All"${{pendingSectorFilter === 'All' ? ' selected' : ''}}>All Sectors</option>`;
    for (const s of allSectors) {{
        html += `<option value="${{escapeHtml(s)}}"${{pendingSectorFilter === s ? ' selected' : ''}}>${{escapeHtml(s)}}</option>`;
    }}
    html += `</select></div>`;

    if (!filtered.length) {{
        html += '<div class="empty-state" style="padding:32px 16px;"><div class="empty-icon">&#128269;</div><div class="empty-text">No recommendations in sector: ' + escapeHtml(pendingSectorFilter) + '</div></div>';
        panel.innerHTML = html;
        return;
    }}
    for (const o of filtered) {{
        const prop = o._proposal || {{}};
        const tech = o._tech_score || {{}};
        const risk = o._risk || {{}};
        const id = o.order_id || o.proposal_id;

        // Core fields
        const ticker = o.ticker || '—';
        const direction = (o.direction || '').toUpperCase();
        const hedgeTicker = o.hedge_ticker || '—';
        const hedgeDir = (o.hedge_direction || 'short').toUpperCase();
        const dirClass = direction === 'LONG' ? 'positive' : 'negative';

        // Pair expression
        const pairExpr = direction === 'LONG' 
            ? `Long ${{ticker}} / Short ${{hedgeTicker}}`
            : `Short ${{ticker}} / Long ${{hedgeTicker}}`;

        // Ratio fields
        const entryRatio = prop.entry_ratio || o.entry_ratio;
        const targetRatio = prop.target_ratio || o.target_ratio;
        const stopRatio = prop.stop_ratio || o.stop_ratio;
        const ratioPctile = prop.ratio_percentile || o.ratio_percentile;

        // Size & Risk
        const sizePctNav = o.size_pct_nav != null ? o.size_pct_nav : null;
        const sizeDisplay = sizePctNav != null ? (sizePctNav * 100).toFixed(1) + '%' : '—';
        const conviction = o.conviction || prop.conviction || '—';
        const trailPct = parseTrailPct(o.stop_loss_method);
        let lossAtTrailBps = '—';
        if (trailPct != null && sizePctNav != null) {{
            lossAtTrailBps = Math.round((trailPct / 100) * sizePctNav * 10000) + ' bps';
        }}

        // Thesis
        const thesis = prop.thesis_summary || prop.portfolio_thesis || o.portfolio_thesis || o.pm_rationale || '—';
        const variant = prop.variant_perception || '';
        const catalyst = prop.catalyst || '';
        const catalystTimeline = prop.catalyst_timeline || '';
        const keyRisks = prop.key_risks || [];

        // Tech & Risk verdicts
        const techScore = tech.technical_score != null ? tech.technical_score : null;
        const riskDecision = risk.decision || 'pending';
        const riskClass = riskDecision.includes('approved') ? 'badge-positive' : riskDecision === 'pending' ? 'badge-neutral' : 'badge-negative';

        html += `
        <div class="pending-card">
            <!-- HEADER: Pair expression + badges -->
            <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:16px;">
                <div>
                    <div style="font-size:1.3em;font-weight:800;color:var(--text-primary);">${{pairExpr}}</div>
                    <div style="font-size:0.78em;color:var(--text-muted);margin-top:2px;">${{o.proposal_id || ''}}</div>
                </div>
                <div style="display:flex;gap:8px;align-items:center;">
                    <span class="badge badge-warning">AWAITING PM</span>
                    ${{techScore != null ? `<span class="badge ${{techScore>=7?'badge-positive':techScore>=5?'badge-neutral':'badge-negative'}}">Tech ${{techScore}}/10</span>` : ''}}
                    <span class="badge ${{riskClass}}">${{riskDecision.toUpperCase()}}</span>
                </div>
            </div>

            <!-- TRADE PARAMETERS: ratio-driven grid -->
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-bottom:16px;padding:14px;background:var(--bg-secondary);border-radius:10px;border:1px solid var(--border);">
                <div><div style="font-size:0.68em;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Size</div><div style="font-size:1.1em;font-weight:700;margin-top:3px;">${{sizeDisplay}} NAV</div></div>
                <div><div style="font-size:0.68em;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Conviction</div><div style="font-size:1.1em;font-weight:700;margin-top:3px;">${{conviction}}/10</div></div>
                <div><div style="font-size:0.68em;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Entry Ratio</div><div style="font-size:1.1em;font-weight:700;margin-top:3px;">${{entryRatio != null ? Number(entryRatio).toFixed(4) : '—'}}</div></div>
                <div><div style="font-size:0.68em;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Target Ratio</div><div style="font-size:1.1em;font-weight:700;margin-top:3px;color:var(--positive);">${{targetRatio != null ? Number(targetRatio).toFixed(4) : '—'}}</div></div>
                <div><div style="font-size:0.68em;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Stop Ratio</div><div style="font-size:1.1em;font-weight:700;margin-top:3px;color:var(--negative);">${{stopRatio != null ? Number(stopRatio).toFixed(4) : '—'}}</div></div>
                <div><div style="font-size:0.68em;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Ratio %ile (52w)</div><div style="font-size:1.1em;font-weight:700;margin-top:3px;">${{ratioPctile != null ? ratioPctile + 'th' : '—'}}</div></div>
                <div><div style="font-size:0.68em;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Loss@Trail</div><div style="font-size:1.1em;font-weight:700;margin-top:3px;">${{lossAtTrailBps}}</div></div>
                <div><div style="font-size:0.68em;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Holding Period</div><div style="font-size:1.1em;font-weight:700;margin-top:3px;">${{escapeHtml(o.expected_holding_period || prop.holding_period || '—')}}</div></div>
            </div>

            <!-- THESIS -->
            <div style="margin-bottom:14px;">
                <div style="font-size:0.72em;font-weight:700;color:var(--brand-gold-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">Thesis</div>
                <div style="font-size:0.9em;color:var(--text-secondary);line-height:1.6;">${{escapeHtml(thesis)}}</div>
            </div>

            <!-- VARIANT PERCEPTION -->
            ${{variant ? `<div style="margin-bottom:14px;">
                <div style="font-size:0.72em;font-weight:700;color:var(--brand-gold-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">Variant Perception</div>
                <div style="font-size:0.88em;color:var(--text-secondary);line-height:1.5;">${{escapeHtml(variant)}}</div>
            </div>` : ''}}

            <!-- CATALYST -->
            ${{catalyst ? `<div style="margin-bottom:14px;">
                <div style="font-size:0.72em;font-weight:700;color:var(--brand-gold-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">Catalyst ${{catalystTimeline ? '(' + escapeHtml(catalystTimeline) + ')' : ''}}</div>
                <div style="font-size:0.88em;color:var(--text-secondary);line-height:1.5;">${{escapeHtml(catalyst)}}</div>
            </div>` : ''}}

            <!-- KEY RISKS -->
            ${{keyRisks.length > 0 ? `<div style="margin-bottom:14px;">
                <div style="font-size:0.72em;font-weight:700;color:var(--brand-gold-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">Key Risks</div>
                <ul style="margin:0;padding-left:16px;font-size:0.85em;color:var(--text-secondary);line-height:1.5;">
                    ${{keyRisks.map(r => `<li>${{escapeHtml(typeof r === 'string' ? r : JSON.stringify(r))}}</li>`).join('')}}
                </ul>
            </div>` : ''}}

            <!-- ACTIONS -->
            <div style="display:flex;gap:12px;margin-top:16px;padding-top:16px;border-top:1px solid var(--border);">
                <button class="btn btn-accept" data-accept-id="${{id}}" onclick="acceptOrder('${{id}}')">Approve &amp; Execute</button>
                <button class="btn btn-deny" data-deny-id="${{id}}" onclick="denyOrder('${{id}}')">Pass</button>
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
        case 'pair': return ((p.ticker || '') + '/' + (p.hedge_ticker || '')).toLowerCase();
        case 'direction': return (p.direction || '').toLowerCase();
        case 'entry': return p.entryRatio || p.entry_price || 0;
        case 'current': return p.currentRatio || p.current_price || 0;
        case 'peak': return p.peakRatio || 0;
        case 'pnl': return p.pnlPct || p.combined_pnl_pct || 0;
        case 'distpeak': return p.distFromPeak || 0;
        case 'trail': return p.trailPct || 0;
        case 'days': {{
            const entryDate = p.entry_date ? new Date(p.entry_date) : null;
            return entryDate ? Math.floor((Date.now() - entryDate.getTime()) / 86400000) : 0;
        }}
        case 'size': return p.size_pct_nav || 0;
        case 'sector': return (p.sector || HEDGE_TO_SECTOR[p.hedge_ticker] || 'Unknown').toLowerCase();
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

    // Ticker filter input
    html += `<div class="section-title">Positions</div>`;
    html += `<input class="position-filter-input" type="text" placeholder="Filter by ticker..." value="${{escapeHtml(positionTickerFilter)}}" oninput="filterPositionsByTicker(this.value)" aria-label="Filter positions by ticker" />`;

    // Use enriched positions from state.derived if available
    const enrichedPositions = (state.derived && state.derived.positions) ? state.derived.positions : [];

    // Apply filter
    let positions = enrichedPositions.length > 0 ? enrichedPositions : allPositions.filter(p => p.status === 'active');
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

    // Table start — ratio-driven columns per spec (Task 3)
    html += `<div class="position-table-wrapper">`;
    html += `<table class="position-table"><thead><tr>`;
    html += sortHeader('Pair', 'pair', false);
    html += sortHeader('Dir', 'direction', false);
    html += sortHeader('Entry Ratio', 'entry', true);
    html += sortHeader('Current Ratio', 'current', true);
    html += sortHeader('Peak', 'peak', true);
    html += sortHeader('Pair P&L%', 'pnl', true);
    html += sortHeader('Dist-Peak%', 'distpeak', true);
    html += sortHeader('Trail%', 'trail', true);
    html += sortHeader('Days', 'days', true);
    html += sortHeader('Size%', 'size', true);
    html += sortHeader('Sector', 'sector', false);
    html += `</tr></thead><tbody>`;

    for (const p of positions) {{
        const ticker = p.ticker || '—';
        const hedge = p.hedge_ticker || '—';
        const pairLabel = hedge !== '—' ? ticker + '/' + hedge : ticker;
        const direction = (p.direction || '').toLowerCase();
        const sizePct = p.size_pct_nav || 0;
        const isExpanded = expandedPositions.has(ticker);

        // Enriched pair-ratio fields
        const entryRatio = p.entryRatio != null ? p.entryRatio.toFixed(4) : '—';
        const currentRatio = p.currentRatio != null ? p.currentRatio.toFixed(4) : '—';
        const peakRatio = p.peakRatio != null ? p.peakRatio.toFixed(4) : '—';
        const pnlPct = p.pnlPct != null ? (p.pnlPct >= 0 ? '+' : '') + p.pnlPct.toFixed(2) + '%' : '—';
        const trailPct = p.trailPct != null ? p.trailPct.toFixed(1) + '%' : '—';
        const distFromPeak = p.distFromPeak != null ? p.distFromPeak.toFixed(2) + '%' : '—';
        const pnlColor = p.pnlPct != null ? pnlState(p.pnlPct / 100) : 'neutral';

        // Days held
        const entryDate = p.entry_date ? new Date(p.entry_date) : null;
        const daysHeld = entryDate ? Math.floor((Date.now() - entryDate.getTime()) / 86400000) : '—';

        // Sector
        const sector = p.sector || HEDGE_TO_SECTOR[p.hedge_ticker] || '—';

        // Direction badge
        const dirBadge = `<span class="dir-badge ${{direction}}">${{direction.toUpperCase()}}</span>`;

        // Trail proximity highlight: amber within 1% of stop, red within 0.5%
        let rowStyle = '';
        if (p.trailPct != null && p.distFromPeak != null) {{
            const distFromStop = Math.abs(p.trailPct) - Math.abs(p.distFromPeak);
            if (distFromStop <= 0.5) rowStyle = 'background:rgba(255,23,68,0.10);';
            else if (distFromStop <= 1.0) rowStyle = 'background:rgba(255,171,0,0.10);';
        }}
        if (p.highlight === 'red') rowStyle = 'background:rgba(255,23,68,0.10);';
        else if (p.highlight === 'amber') rowStyle = 'background:rgba(255,171,0,0.10);';

        // Dist-Peak color coding (negative distance = drawdown)
        let distPeakColor = '';
        if (p.distFromPeak != null) {{
            if (Math.abs(p.distFromPeak) <= 0.5) distPeakColor = ' style="color:var(--pnl-negative);font-weight:700;"';
            else if (Math.abs(p.distFromPeak) <= 1.0) distPeakColor = ' style="color:var(--warning-amber,#ffab00);font-weight:600;"';
        }}

        html += `<tr class="position-row" onclick="togglePositionDetail('${{ticker}}')" aria-expanded="${{isExpanded}}" title="Click to expand details" style="${{rowStyle}}">`;
        html += `<td style="font-weight:700;white-space:nowrap;">${{pairLabel}}</td>`;
        html += `<td>${{dirBadge}}</td>`;
        html += `<td class="num-col">${{entryRatio}}</td>`;
        html += `<td class="num-col">${{currentRatio}}</td>`;
        html += `<td class="num-col">${{peakRatio}}</td>`;
        html += `<td class="num-col ${{pnlColor}}" style="font-weight:700;">${{pnlPct}}</td>`;
        html += `<td class="num-col"${{distPeakColor}}>${{distFromPeak}}</td>`;
        html += `<td class="num-col">${{trailPct}}</td>`;
        html += `<td class="num-col">${{daysHeld}}</td>`;
        html += `<td class="num-col">${{(sizePct * 100).toFixed(1)}}%</td>`;
        html += `<td style="font-size:0.85em;">${{sector}}</td>`;
        html += `</tr>`;

        // Expandable detail row
        if (isExpanded) {{
            html += `<tr class="position-detail-row"><td colspan="11">`;
            html += renderPositionDetailPanel(p);
            html += `</td></tr>`;
        }}
    }}

    // Summary row — gross, net, avg P&L
    let grossExposure = 0;
    let netExposure = 0;
    let pnlSum = 0;
    let pnlCount = 0;
    for (const p of positions) {{
        const size = p.size_pct_nav || 0;
        const dir = (p.direction || '').toLowerCase();
        grossExposure += Math.abs(size);
        netExposure += dir === 'short' ? -Math.abs(size) : Math.abs(size);
        if (p.pnlPct != null) {{
            pnlSum += p.pnlPct;
            pnlCount++;
        }}
    }}
    const avgPnl = pnlCount > 0 ? pnlSum / pnlCount : 0;
    const avgPnlColor = avgPnl >= 0 ? 'var(--pnl-positive, #00e676)' : 'var(--pnl-negative, #ff1744)';

    html += `</tbody><tfoot><tr class="summary-row" style="border-top:2px solid var(--border-color, #333);background:rgba(255,255,255,0.03);font-weight:700;">`;
    html += `<td style="font-weight:700;">Total</td>`;
    html += `<td></td>`;
    html += `<td></td>`;
    html += `<td></td>`;
    html += `<td></td>`;
    html += `<td class="num-col" style="color:${{avgPnlColor}};font-weight:700;">${{(avgPnl >= 0 ? '+' : '') + avgPnl.toFixed(2)}}% avg</td>`;
    html += `<td></td>`;
    html += `<td></td>`;
    html += `<td></td>`;
    html += `<td class="num-col" style="font-weight:700;">G:${{(grossExposure * 100).toFixed(1)}}% N:${{(netExposure * 100).toFixed(1)}}%</td>`;
    html += `<td></td>`;
    html += `</tr></tfoot></table></div>`;

    // Equity Curve sub-section (moved from Overview per spec)
    html += `<div class="section-title" style="margin-top:24px;">Equity Curve</div>`;
    html += renderEquityChart();

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
    let flipCondition = 'Not specified';
    let convictionMemo = 'Memo not available';

    // If position has a proposalId, try to find matching proposal data
    const matchingPending = (state.pending || []).find(r => r.ticker === ticker);
    if (matchingPending && matchingPending._proposal) {{
        thesis = matchingPending._proposal.thesis_summary || matchingPending._proposal.thesisSummary || '';
        entryRationale = matchingPending._proposal.variant_perception || matchingPending._proposal.variantPerception || '';
        exitCriteria = matchingPending._proposal.catalyst || '';
        const risks = matchingPending._proposal.key_risks || matchingPending._proposal.keyRisks || [];
        riskTriggers = Array.isArray(risks) ? risks.join('; ') : risks;
        // Flip condition (Task 4.3)
        if (matchingPending._proposal.flip_condition) {{
            flipCondition = matchingPending._proposal.flip_condition;
        }}
        // Conviction memo (Task 4.3)
        if (matchingPending._proposal.conviction_memo || matchingPending._proposal.why_this_deserves_size) {{
            convictionMemo = matchingPending._proposal.conviction_memo || matchingPending._proposal.why_this_deserves_size;
        }}
    }}

    // Also search trade_journal for proposal data
    const journalEntry = (state.book.trade_journal || []).find(e => {{
        const o = e.order || {{}};
        return o.ticker === ticker;
    }});
    if (journalEntry && journalEntry.order) {{
        const order = journalEntry.order;
        if (!thesis && order.portfolio_thesis) thesis = order.portfolio_thesis;
        if (!entryRationale && order.pm_rationale) entryRationale = order.pm_rationale;
        if (order.flip_condition) flipCondition = order.flip_condition;
        if (order.conviction_memo || order.why_this_deserves_size) {{
            convictionMemo = order.conviction_memo || order.why_this_deserves_size;
        }}
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

    // Flip Condition (Task 4.3)
    html += `<div class="pdp-section" style="grid-column:1/-1;"><div class="pdp-label">Flip Condition</div><div class="pdp-value" style="color:${{flipCondition === 'Not specified' ? 'var(--text-muted)' : 'var(--warning)'}};">${{escapeHtml(flipCondition)}}</div></div>`;

    // Risk triggers
    if (riskTriggers) {{
        html += `<div class="pdp-section"><div class="pdp-label">Risk Triggers</div><div class="pdp-value">${{escapeHtml(riskTriggers)}}</div></div>`;
    }}

    // Conviction Memo (Task 4.3) — only for high-conviction positions
    if (p.isHighConviction) {{
        html += `<div class="pdp-section" style="grid-column:1/-1;border-top:1px solid var(--border);padding-top:12px;margin-top:8px;">
            <div class="pdp-label" style="color:var(--brand-gold);">Why This Deserves Size</div>
            <div class="pdp-value">${{escapeHtml(convictionMemo)}}</div>
        </div>`;
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
    const cols = ['Pair','Dir','Entry Ratio','Current Ratio','Peak','Pair P&L%','Dist-Peak%','Trail%','Days','Size%','Sector'];
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

function getJournalDateGroup(timestamp) {{
    if (!timestamp) return 'Earlier';
    try {{
        const now = new Date();
        const entryDate = new Date(timestamp);
        if (isNaN(entryDate.getTime())) return 'Earlier';
        const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const yesterdayStart = new Date(todayStart);
        yesterdayStart.setDate(yesterdayStart.getDate() - 1);
        // Start of week (Monday)
        const weekStart = new Date(todayStart);
        const dayOfWeek = todayStart.getDay();
        const daysToMon = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
        weekStart.setDate(weekStart.getDate() - daysToMon);

        if (entryDate >= todayStart) return 'Today';
        if (entryDate >= yesterdayStart) return 'Yesterday';
        if (entryDate >= weekStart) return 'This Week';
        return 'Earlier';
    }} catch(err) {{
        return 'Earlier';
    }}
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
    // Compute cumulative P&L from oldest to newest for closed trades
    const journalChron = [...journal].reverse(); // oldest first
    const cumPnlMap = new Map();
    let cumPnlRunning = 0;
    for (const e of journalChron) {{
        const o = e.order || {{}};
        const entryId = o.order_id || o.proposal_id || e.timestamp || (o.ticker || e.ticker || '');
        if (e.action === 'close' && e.realized_pnl_pct != null) {{
            cumPnlRunning += e.realized_pnl_pct;
            cumPnlMap.set(entryId, cumPnlRunning);
        }}
    }}

    let html = '<div class="section-title">Trade Journal</div><table class="data-table"><thead><tr><th>Action</th><th>Ticker</th><th>Direction</th><th>Conviction</th><th>IC</th><th>Size</th><th>Thesis</th><th>Hedge</th><th>Entry</th><th>P&L</th><th>Cum P&L</th><th>Timestamp</th></tr></thead><tbody>';
    let currentGroup = '';
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

        // Date grouping header
        const group = getJournalDateGroup(e.timestamp);
        if (group !== currentGroup) {{
            currentGroup = group;
            html += `<tr class="journal-group-header"><td colspan="12">${{group}}</td></tr>`;
        }}

        // Extract order fields
        const conviction = o.conviction != null ? o.conviction : '—';
        const sizePct = o.size_pct_nav != null ? (o.size_pct_nav * 100).toFixed(1) + '%' : '—';
        const thesisFull = o.portfolio_thesis || '';
        const thesisTrunc = thesisFull.length > 40 ? thesisFull.substring(0, 40) + '...' : thesisFull || '—';

        // Build inline IC badges (Tech Score + Risk Decision)
        const techScore = e.tech_score;
        const riskDec = e.risk_decision;
        let icBadges = '';
        if (techScore && techScore.technical_score != null) {{
            const tsClass = techScore.technical_score >= 7 ? 'badge-positive' : techScore.technical_score >= 5 ? 'badge-warning' : 'badge-negative';
            icBadges += `<span class="badge ${{tsClass}}" style="font-size:0.72em;padding:2px 5px;margin-right:4px;">Tech ${{techScore.technical_score}}/10</span>`;
        }}
        if (riskDec && riskDec.decision) {{
            const rdClass = riskDec.decision === 'approved' ? 'badge-positive' : 'badge-negative';
            icBadges += `<span class="badge ${{rdClass}}" style="font-size:0.72em;padding:2px 5px;">${{riskDec.decision.toUpperCase()}}</span>`;
        }}
        if (!icBadges) icBadges = '<span style="color:var(--text-muted);font-size:0.78em;">—</span>';

        html += `<tr class="position-row" onclick="toggleJournalDetail('${{entryId}}')" aria-expanded="${{isExpanded}}" title="Click to expand details" style="cursor:pointer;">
            <td><span class="badge ${{actionClass}}">${{(e.action||'').toUpperCase()}}</span></td>
            <td style="font-weight:600;">${{ticker}}</td>
            <td>${{dir.toUpperCase()}}</td>
            <td>${{conviction !== '—' ? conviction + '/10' : '—'}}</td>
            <td style="white-space:nowrap;">${{icBadges}}</td>
            <td>${{sizePct}}</td>
            <td style="font-size:0.82em;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${{escapeHtml(thesisFull)}}">${{escapeHtml(thesisTrunc)}}</td>
            <td>${{hedge}}</td>
            <td>${{ep ? '$'+Number(ep).toFixed(2) : '—'}}</td>
            <td class="${{pnlState(pnl)}}">${{pnl != null ? formatPctSigned(pnl) : '—'}}</td>
            <td class="${{cumPnlMap.has(entryId) ? (cumPnlMap.get(entryId) >= 0 ? 'positive' : 'negative') : ''}}">${{cumPnlMap.has(entryId) ? formatPctSigned(cumPnlMap.get(entryId)) : '—'}}</td>
            <td style="font-size:0.82em;color:var(--text-muted);" title="${{e.timestamp||''}}">${{formatTimestampET(e.timestamp)}}</td>
        </tr>`;

        // Expandable detail row
        if (isExpanded) {{
            html += `<tr class="position-detail-row"><td colspan="12">`;
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

    // Linked Tech Score (stored in journal entry)
    const techScore = entry.tech_score;
    if (techScore && techScore.technical_score != null) {{
        html += `<div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border);">`;
        html += `<div class="pdp-label" style="margin-bottom:8px;">Technical Score</div>`;
        html += `<div style="display:flex;align-items:center;gap:12px;">`;
        html += `<span class="badge ${{techScore.technical_score>=7?'badge-positive':techScore.technical_score>=5?'badge-warning':'badge-negative'}}">${{techScore.technical_score}}/10</span>`;
        html += `<span style="font-size:0.85em;color:var(--text-secondary);">${{escapeHtml(techScore.timing_rationale || techScore.trend_alignment || '')}}</span>`;
        html += `</div></div>`;
    }}

    // Linked Risk Decision (stored in journal entry)
    const riskDec = entry.risk_decision;
    if (riskDec && riskDec.decision) {{
        const riskClass = riskDec.decision === 'approved' ? 'badge-positive' : 'badge-negative';
        html += `<div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border);">`;
        html += `<div class="pdp-label" style="margin-bottom:8px;">Risk Decision</div>`;
        html += `<div style="display:flex;align-items:center;gap:12px;">`;
        html += `<span class="badge ${{riskClass}}">${{riskDec.decision.toUpperCase()}}</span>`;
        html += `<span style="font-size:0.85em;color:var(--text-secondary);">${{escapeHtml(riskDec.rationale || '')}}</span>`;
        html += `</div></div>`;
    }}

    // Linked Debates (stored in journal entry)
    const debates = entry.debates || [];
    if (debates.length > 0) {{
        html += `<div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border);">`;
        html += `<div class="pdp-label" style="margin-bottom:8px;">Agent Debate (${{debates.length}} entries)</div>`;
        for (const d of debates.slice(0, 4)) {{
            const stanceClass = d.stance==='support' ? 'badge-blue' : d.stance==='challenge' ? 'badge-negative' : 'badge-neutral';
            html += `<div style="margin-bottom:6px;font-size:0.85em;">`;
            html += `<span class="badge ${{stanceClass}}" style="margin-right:6px;">${{(d.agent_id||'').replace(/_/g,' ')}}: ${{(d.stance||'').toUpperCase()}}</span>`;
            html += `<span style="color:var(--text-secondary);">${{escapeHtml((d.argument||'').substring(0, 120))}}${{(d.argument||'').length > 120 ? '...' : ''}}</span>`;
            html += `</div>`;
        }}
        if (debates.length > 4) {{
            html += `<div style="font-size:0.78em;color:var(--text-muted);">+ ${{debates.length - 4}} more entries</div>`;
        }}
        html += `</div>`;
    }}

    html += `</div>`;  // position-detail-panel
    return html;
}}

function renderDebate() {{
    const panel = document.getElementById('panel-debate');
    if (!state.debates.length) {{
        panel.innerHTML = '<div class="empty-state"><div class="empty-icon">&#128172;</div><div class="empty-text">No debate records yet.</div></div>';
        return;
    }}

    // Group debates by proposal_id
    const grouped = {{}};
    for (const d of state.debates) {{
        const pid = d.proposal_id || 'unknown';
        if (!grouped[pid]) grouped[pid] = [];
        grouped[pid].push(d);
    }}

    let html = '<div class="section-title">Agent Debate by Proposal</div>';

    for (const [pid, debates] of Object.entries(grouped)) {{
        // Find the ticker from the proposal_id or from pending orders
        const matchingOrder = (state.pending || []).find(o => o.proposal_id === pid);
        const ticker = matchingOrder ? matchingOrder.ticker : pid.split('_').slice(-1)[0] || '—';
        const direction = matchingOrder ? matchingOrder.direction : '';

        html += `<div class="pending-card" style="margin-bottom:20px;">`;
        html += `<div class="pending-header"><h3>${{escapeHtml(pid)}}</h3>${{direction ? `<span class="badge ${{direction==='long'?'badge-positive':'badge-negative'}}">${{direction.toUpperCase()}}</span>` : ''}}</div>`;

        // Sort by round then by stance
        const sorted = [...debates].sort((a, b) => (a.round || 0) - (b.round || 0));

        for (const d of sorted) {{
            const stanceClass = d.stance==='support' ? 'badge-blue' : d.stance==='challenge' ? 'badge-negative' : d.stance==='defend' ? 'badge-neutral' : 'badge-neutral';
            html += `<div class="debate-entry" style="margin-bottom:8px;">
                <div class="debate-header">
                    <span class="debate-agent">${{(d.agent_id||'').replace(/_/g,' ').replace(/\\b\\w/g,c=>c.toUpperCase())}}</span>
                    <span class="badge ${{stanceClass}}">${{(d.stance||'').toUpperCase()}}</span>
                    <span style="font-size:0.75em;color:var(--text-muted);margin-left:auto;">Round ${{d.round||''}}</span>
                    ${{d.revised_conviction ? `<span style="margin-left:12px;font-size:0.8em;color:var(--text-muted);">Conv: <strong>${{d.revised_conviction}}/10</strong></span>` : ''}}
                </div>
                <div class="debate-body">${{escapeHtml(d.argument||'')}}</div>
            </div>`;
        }}

        html += `</div>`;
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

    let html = '';

    // ─── Factor Beta Table (Task 5.1) ─────────────────────────────────────────
    html += `<div class="section-title">Factor Exposure (Book Betas)</div>`;
    const FACTOR_DISPLAY = {{
        'USD_DXY': 'USD / DXY', 'SPX': 'SPX', 'RATES_10Y': 'Rates / 10Y',
        'VIX': 'VIX', 'GROWTH_VALUE': 'Growth / Value', 'CRUDE_CL1': 'Crude / CL1',
        'LARGE_SMALL': 'Large / Small', 'HY_CREDIT': 'HY Credit', 'GOLD_XAU': 'Gold / XAU'
    }};
    const FACTOR_KEYS = ['USD_DXY', 'SPX', 'RATES_10Y', 'VIX', 'GROWTH_VALUE', 'CRUDE_CL1', 'LARGE_SMALL', 'HY_CREDIT', 'GOLD_XAU'];

    html += `<table class="data-table" style="margin-bottom:24px;"><thead><tr><th>Factor</th><th style="text-align:right;">Beta</th><th>Status</th></tr></thead><tbody>`;
    if (state.factors && state.factors.available) {{
        for (const key of FACTOR_KEYS) {{
            const beta = state.factors.factors[key];
            const betaVal = beta != null ? beta.toFixed(2) : '—';
            const cls = classifyBeta(beta);
            let statusBadge = '';
            if (cls === 'red') statusBadge = '<span class="badge badge-negative">BREACH</span>';
            else if (cls === 'amber') statusBadge = '<span class="badge badge-warning">WARNING</span>';
            else statusBadge = '<span class="badge badge-neutral">OK</span>';
            const cellStyle = cls === 'red' ? 'background:rgba(255,23,68,0.08);' : cls === 'amber' ? 'background:rgba(255,171,0,0.08);' : '';
            html += `<tr><td>${{FACTOR_DISPLAY[key] || key}}</td><td style="text-align:right;font-weight:600;${{cellStyle}}">${{betaVal}}</td><td>${{statusBadge}}</td></tr>`;
        }}
    }} else {{
        for (const key of FACTOR_KEYS) {{
            html += `<tr><td>${{FACTOR_DISPLAY[key] || key}}</td><td style="text-align:right;color:var(--text-muted);">—</td><td><span class="badge badge-neutral">pending</span></td></tr>`;
        }}
    }}
    html += `</tbody></table>`;

    // ─── Concentration Limits Table (Task 5.2) ────────────────────────────────
    html += `<div class="section-title">Concentration Limits</div>`;
    const concentration = (state.derived && state.derived.concentration) ? state.derived.concentration : {{}};
    const sectorEntries = Object.entries(concentration);

    if (sectorEntries.length > 0) {{
        html += `<table class="data-table" style="margin-bottom:24px;"><thead><tr><th>Sector</th><th style="text-align:right;">Positions</th><th style="text-align:right;">NAV %</th><th>Status</th></tr></thead><tbody>`;
        for (const [sector, data] of sectorEntries) {{
            const countDisplay = data.count + ' / 4 max';
            const navDisplay = (data.navPct * 100).toFixed(1) + '% / 15% max';
            let statusBadge = '<span class="badge badge-neutral">OK</span>';
            let rowStyle = '';
            if (data.highlight === 'red') {{
                statusBadge = '<span class="badge badge-negative">AT LIMIT</span>';
                rowStyle = 'background:rgba(255,23,68,0.08);';
            }} else if (data.highlight === 'amber') {{
                statusBadge = '<span class="badge badge-warning">NEAR LIMIT</span>';
                rowStyle = 'background:rgba(255,171,0,0.08);';
            }}
            html += `<tr style="${{rowStyle}}"><td style="font-weight:600;">${{sector}}</td><td style="text-align:right;">${{countDisplay}}</td><td style="text-align:right;">${{navDisplay}}</td><td>${{statusBadge}}</td></tr>`;
        }}
        html += `</tbody></table>`;
    }} else {{
        html += `<div style="color:var(--text-muted);font-size:0.88em;margin-bottom:24px;">No active positions for concentration analysis.</div>`;
    }}

    // Country Concentration placeholder
    html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:24px;">
        <div style="font-size:0.78em;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px;">Country Concentration</div>
        <div style="color:var(--text-muted);font-size:0.88em;">Country data pending</div>
    </div>`;

    // ─── Risk Assessments by Proposal ───────────────────────────────────────────
    const validRisks = (state.risks || []).filter(r => r.decision && !r.error);
    if (!validRisks.length) {{
        html += '<div class="section-title">Risk Assessments</div>';
        html += '<div style="color:var(--text-muted);font-size:0.88em;margin-bottom:24px;">No risk assessments yet. Risk evaluations will appear after proposals pass through the pipeline.</div>';
    }} else {{
        html += '<div class="section-title">Risk Assessments by Proposal</div>';
        for (const risk of validRisks) {{
            const decClass = risk.decision === 'approved' ? 'badge-positive' : 'badge-negative';
            const betas = risk.projected_factor_betas || {{}};

            let factorHtml = '';
            for (const [k, v] of Object.entries(betas)) {{
                const cls = v > 0.03 ? 'positive' : v < -0.03 ? 'negative' : 'neutral';
                factorHtml += `<div class="factor-item"><div class="factor-name">${{k}}</div><div class="factor-value ${{cls}}">${{v > 0 ? '+' : ''}}${{typeof v === 'number' ? v.toFixed(3) : v}}</div></div>`;
            }}

            let warningsHtml = '';
            for (const w of (risk.risk_warnings || [])) {{
                warningsHtml += `<span class="badge badge-warning" style="margin-right:6px;margin-bottom:4px;">${{escapeHtml(w)}}</span>`;
            }}

            html += `
            <div class="pending-card" style="margin-bottom:16px;">
                <div class="pending-header"><h3>${{escapeHtml(risk.proposal_id||'—')}}</h3><span class="badge ${{decClass}}">${{(risk.decision||'').toUpperCase()}}</span></div>
                <p style="font-size:0.9em;color:var(--text-secondary);line-height:1.6;margin-bottom:12px;">${{escapeHtml(risk.rationale||'')}}</p>
                <div class="metrics-grid">
                    <div class="metric-card" style="padding:12px;"><div class="metric-label">Size OK</div><div class="metric-value ${{risk.position_size_ok?'positive':'negative'}}" style="font-size:1.1em;">${{risk.position_size_ok?'&#10003;':'&#10007;'}}</div></div>
                    <div class="metric-card" style="padding:12px;"><div class="metric-label">Hedge Valid</div><div class="metric-value ${{risk.hedge_present_and_valid?'positive':'negative'}}" style="font-size:1.1em;">${{risk.hedge_present_and_valid?'&#10003;':'&#10007;'}}</div></div>
                    <div class="metric-card" style="padding:12px;"><div class="metric-label">Sector OK</div><div class="metric-value ${{risk.sector_concentration_ok?'positive':'negative'}}" style="font-size:1.1em;">${{risk.sector_concentration_ok?'&#10003;':'&#10007;'}}</div></div>
                </div>
                ${{factorHtml ? `<div style="margin-top:12px;"><div style="font-size:0.72em;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin-bottom:8px;">Factor Betas</div><div class="factor-grid">${{factorHtml}}</div></div>` : ''}}
                ${{warningsHtml ? `<div style="margin-top:12px;display:flex;flex-wrap:wrap;">${{warningsHtml}}</div>` : ''}}
            </div>`;
        }}
    }}

    panel.innerHTML = html;
}}

function renderTechnical() {{
    const panel = document.getElementById('panel-technical');
    const validScores = (state.scores || []).filter(s => s.technical_score != null && !s.error);
    if (!validScores.length) {{
        panel.innerHTML = '<div class="empty-state"><div class="empty-icon">&#128200;</div><div class="empty-text">No technical scores yet.</div></div>';
        return;
    }}

    let html = '<div class="section-title">Technical Scores by Proposal</div>';

    for (const scoreData of validScores) {{
        const score = scoreData.technical_score || 0;
        const scorePct = score * 10;
        const pid = scoreData.proposal_id || '—';
        // Try to find the ticker from the proposal_id or from the score data
        const ticker = scoreData.ticker || pid.replace(/^(fund_|macro_|tech_)/, '').split('_')[0].toUpperCase() || '—';

        let signalsHtml = '';
        for (const s of (scoreData.active_signals || [])) {{
            const name = (s.signal||'').replace(/_/g,' ').replace(/\\b\\w/g,c=>c.toUpperCase());
            const val = s.value ? ` (${{s.value}})` : '';
            const note = s.note ? ` — ${{s.note}}` : '';
            signalsHtml += `<div class="signal-chip"><span class="signal-dot ${{s.strength||'moderate'}}"></span>${{name}}${{val}}</div>`;
        }}

        let levelsHtml = '';
        const supports = scoreData.support_levels || [];
        const resistances = scoreData.resistance_levels || [];
        for (const r of resistances) levelsHtml += `<div class="factor-item" style="border-color:rgba(255,23,68,0.3);"><div class="factor-name">Resistance</div><div class="factor-value negative">${{typeof r === 'number' ? '$'+r.toFixed(2) : r}}</div></div>`;
        for (const s of supports) levelsHtml += `<div class="factor-item" style="border-color:rgba(0,200,83,0.3);"><div class="factor-name">Support</div><div class="factor-value positive">${{typeof s === 'number' ? '$'+s.toFixed(2) : s}}</div></div>`;

        html += `
        <div class="pending-card" style="margin-bottom:20px;">
            <div class="pending-header"><h3>${{escapeHtml(pid)}}</h3><span class="badge ${{score>=7?'badge-positive':score>=5?'badge-warning':'badge-negative'}}">Score: ${{score}}/10</span></div>
            <div style="margin:16px 0;">
                <div style="display:flex;justify-content:space-between;font-size:0.78em;color:var(--text-muted);margin-bottom:4px;"><span>Bearish</span><span>Neutral</span><span>Bullish</span></div>
                <div style="width:100%;height:12px;background:var(--bg-secondary);border-radius:6px;overflow:hidden;">
                    <div style="width:${{scorePct}}%;height:100%;background:linear-gradient(90deg,var(--negative),var(--warning),var(--positive));border-radius:6px;transition:width 0.8s ease;"></div>
                </div>
            </div>
            <div class="metrics-grid">
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Trend</div><div class="metric-value" style="font-size:1em;text-transform:capitalize;">${{scoreData.trend_alignment||'—'}}</div></div>
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Momentum</div><div class="metric-value" style="font-size:1em;text-transform:capitalize;">${{(scoreData.momentum_regime||'—').replace(/_/g,' ')}}</div></div>
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Timing</div><div class="metric-value" style="font-size:1em;text-transform:capitalize;">${{scoreData.timing_recommendation||'—'}}</div></div>
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Volume</div><div class="metric-value ${{scoreData.volume_confirmation?'positive':'negative'}}" style="font-size:1em;">${{scoreData.volume_confirmation?'Confirmed':'No'}}</div></div>
            </div>
            ${{scoreData.timing_rationale ? `<div style="margin-top:12px;font-size:0.88em;color:var(--text-secondary);line-height:1.6;"><strong>Rationale:</strong> ${{escapeHtml(scoreData.timing_rationale)}}</div>` : ''}}
            ${{signalsHtml ? `<div style="margin-top:12px;"><div style="font-size:0.72em;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin-bottom:8px;">Signals</div><div class="signal-list">${{signalsHtml}}</div></div>` : ''}}
            ${{levelsHtml ? `<div style="margin-top:12px;"><div style="font-size:0.72em;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin-bottom:8px;">Key Levels</div><div class="factor-grid">${{levelsHtml}}</div></div>` : ''}}
            <div class="metrics-grid" style="margin-top:12px;">
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Entry</div><div class="metric-value" style="font-size:1.1em;">${{scoreData.suggested_entry ? '$'+scoreData.suggested_entry.toFixed(2) : '—'}}</div></div>
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Stop</div><div class="metric-value negative" style="font-size:1.1em;">${{scoreData.suggested_stop_loss ? '$'+scoreData.suggested_stop_loss.toFixed(2) : '—'}}</div></div>
                <div class="metric-card" style="padding:14px;"><div class="metric-label">Target</div><div class="metric-value positive" style="font-size:1.1em;">${{scoreData.suggested_take_profit ? '$'+scoreData.suggested_take_profit.toFixed(2) : '—'}}</div></div>
            </div>
        </div>`;
    }}

    panel.innerHTML = html;
}}

// ─── CALENDAR TAB (Task 8.1) ────────────────────────────────────────────────
function renderCalendar() {{
    const panel = document.getElementById('panel-calendar');
    if (!panel) return;

    if (!state.calendar || state.calendar.empty) {{
        panel.innerHTML = `<div class="empty-state">
            <div class="empty-icon">&#128197;</div>
            <div class="empty-text">No calendar data available</div>
        </div>`;
        return;
    }}

    const cal = state.calendar;
    let html = '';

    // Macro releases
    html += `<div class="section-title">Macro Releases</div>`;
    if (cal.macro && cal.macro.length > 0) {{
        html += `<table class="data-table" style="margin-bottom:24px;"><thead><tr><th>Day</th><th>Time</th><th>Currency</th><th>Release</th><th>Consensus</th></tr></thead><tbody>`;
        for (const e of cal.macro) {{
            html += `<tr><td>${{escapeHtml(e.day || e.date || '—')}}</td><td>${{escapeHtml(e.time || '—')}}</td><td style="font-weight:600;">${{escapeHtml(e.currency || '—')}}</td><td>${{escapeHtml(e.release || e.event || '—')}}</td><td>${{escapeHtml(e.consensus || '—')}}</td></tr>`;
        }}
        html += `</tbody></table>`;
    }} else {{
        html += `<div style="color:var(--text-muted);font-size:0.88em;margin-bottom:24px;">No macro releases scheduled.</div>`;
    }}

    // CB Decisions
    html += `<div class="section-title">Central Bank Decisions</div>`;
    if (cal.cb && cal.cb.length > 0) {{
        html += `<table class="data-table" style="margin-bottom:24px;"><thead><tr><th>Date</th><th>Currency</th><th>Expected Action</th></tr></thead><tbody>`;
        for (const e of cal.cb) {{
            html += `<tr><td>${{escapeHtml(e.date || '—')}}</td><td style="font-weight:600;">${{escapeHtml(e.currency || '—')}}</td><td>${{escapeHtml(e.action || '—')}}</td></tr>`;
        }}
        html += `</tbody></table>`;
    }} else {{
        html += `<div style="color:var(--text-muted);font-size:0.88em;margin-bottom:24px;">No CB decisions scheduled.</div>`;
    }}

    // Earnings
    html += `<div class="section-title">Earnings</div>`;
    if (cal.earnings && cal.earnings.length > 0) {{
        html += `<table class="data-table" style="margin-bottom:24px;"><thead><tr><th>Date</th><th>Ticker</th><th>Timing</th></tr></thead><tbody>`;
        for (const e of cal.earnings) {{
            html += `<tr><td>${{escapeHtml(e.date || '—')}}</td><td style="font-weight:700;">${{escapeHtml(e.ticker || '—')}}</td><td>${{escapeHtml(e.timing || '—')}}</td></tr>`;
        }}
        html += `</tbody></table>`;
    }} else {{
        html += `<div style="color:var(--text-muted);font-size:0.88em;margin-bottom:24px;">No earnings events scheduled.</div>`;
    }}

    // Holidays
    html += `<div class="section-title">Market Holidays</div>`;
    if (cal.holidays && cal.holidays.length > 0) {{
        html += `<table class="data-table" style="margin-bottom:24px;"><thead><tr><th>Date</th><th>Holiday</th><th>Type</th></tr></thead><tbody>`;
        for (const e of cal.holidays) {{
            html += `<tr><td>${{escapeHtml(e.date || '—')}}</td><td>${{escapeHtml(e.name || '—')}}</td><td>${{escapeHtml(e.type || '—')}}</td></tr>`;
        }}
        html += `</tbody></table>`;
    }} else {{
        html += `<div style="color:var(--text-muted);font-size:0.88em;margin-bottom:24px;">No holidays scheduled.</div>`;
    }}

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
        let ts = formatTimestampET(log.timestamp);
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

    // Initial capital reference line (horizontal dashed)
    const refY = scaleY(initialCapital);
    const refLine = `<line x1="${{PAD_L}}" y1="${{refY}}" x2="${{W-PAD_R}}" y2="${{refY}}" stroke="var(--brand-gold-dim)" stroke-width="1" stroke-dasharray="5,4" opacity="0.7"/>
    <text x="${{W-PAD_R+2}}" y="${{refY-4}}" fill="var(--brand-gold-dim)" font-size="9" text-anchor="start">${{formatDollar(initialCapital)}}</text>`;

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
function formatTimestampET(ts) {{
    if (!ts) return '—';
    try {{
        const d = new Date(ts);
        if (isNaN(d.getTime())) return '—';
        const etStr = d.toLocaleString('en-US', {{ timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false }});
        return etStr + ' ET';
    }} catch(e) {{
        return '—';
    }}
}}

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

// ─── BOOTSTRAP ALIGNMENT: DERIVED METRICS ────────────────────────────────────

const HEDGE_TO_SECTOR = {{
    'RSPG': 'Energy', 'RSPM': 'Materials', 'RSPN': 'Industrials',
    'RSPD': 'Consumer Discretionary', 'RSPS': 'Consumer Staples',
    'RSPH': 'Health Care', 'RSPF': 'Financials', 'RSPT': 'Information Technology',
    'RSPC': 'Communication Services', 'RSPU': 'Utilities', 'RSPR': 'Real Estate'
}};

function round4(x) {{
    if (x == null) return null;
    return Math.round(x * 10000) / 10000;
}}

function parseTrailPct(stopLossMethod) {{
    if (!stopLossMethod) return null;
    const match = stopLossMethod.match(/(\\d+\\.?\\d*)\\s*%/);
    return match ? parseFloat(match[1]) : null;
}}

function computeDerivedMetrics(state) {{
    const positions = (state.book.positions || []).filter(p => p.status === 'active').map(pos => {{
        const entryRatio = (pos.entry_price && pos.hedge_entry_price && pos.hedge_entry_price > 0)
            ? round4(pos.entry_price / pos.hedge_entry_price) : null;
        const currentRatio = (pos.current_price && pos.hedge_current_price && pos.hedge_current_price > 0)
            ? round4(pos.current_price / pos.hedge_current_price) : null;
        
        // Peak ratio: use stored value or default to max of entry/current
        let peakRatio = pos.peak_ratio || entryRatio;
        if (currentRatio != null && peakRatio != null) {{
            const dir = (pos.direction || 'long').toLowerCase();
            if (dir === 'long') {{
                peakRatio = Math.max(peakRatio, currentRatio);
            }} else {{
                peakRatio = Math.min(peakRatio, currentRatio);
            }}
        }}
        
        // P&L from ratio (not individual legs)
        let pnlPct = null;
        if (entryRatio != null && currentRatio != null && entryRatio !== 0) {{
            const dir = (pos.direction || 'long').toLowerCase();
            if (dir === 'long') {{
                pnlPct = ((currentRatio - entryRatio) / entryRatio) * 100;
            }} else {{
                pnlPct = ((entryRatio - currentRatio) / entryRatio) * 100;
            }}
        }}
        
        // Distance from peak (how far the position has pulled back from its best)
        let distFromPeak = null;
        if (peakRatio != null && currentRatio != null && peakRatio !== 0) {{
            const dir = (pos.direction || 'long').toLowerCase();
            if (dir === 'long') {{
                distFromPeak = ((peakRatio - currentRatio) / peakRatio) * 100;
            }} else {{
                distFromPeak = ((currentRatio - peakRatio) / peakRatio) * 100;
            }}
        }}
        
        // Distance to target (+5% from entry ratio)
        let distToTarget = null;
        if (entryRatio != null && currentRatio != null && currentRatio !== 0) {{
            const targetRatio = entryRatio * 1.05;
            distToTarget = ((targetRatio - currentRatio) / currentRatio) * 100;
        }}
        
        // Trail percentage
        const trailPct = parseTrailPct(pos.stop_loss_method);
        
        // Loss at trail in bps of NAV
        let lossAtTrail = null;
        if (trailPct != null && pos.size_pct_nav != null) {{
            lossAtTrail = Math.round((trailPct / 100) * pos.size_pct_nav * 10000);
        }}
        
        // Trail proximity highlight
        const highlight = classifyProximity(distFromPeak, trailPct);
        
        // High conviction tier
        const isHighConviction = (pos.size_pct_nav || 0) > 0.05;
        
        // Sector from hedge ticker
        const sector = HEDGE_TO_SECTOR[pos.hedge_ticker] || 'Unknown';
        
        return {{
            ...pos,
            entryRatio, currentRatio, peakRatio, pnlPct,
            distFromPeak, distToTarget, trailPct, lossAtTrail,
            highlight, isHighConviction, sector
        }};
    }});
    
    // Total loss at trail (sum across all positions)
    const totalLossAtTrail = positions.reduce((sum, p) => sum + (p.lossAtTrail || 0), 0);
    
    // Concentration by sector
    const concentration = computeConcentration(positions);
    
    return {{ positions, totalLossAtTrail, concentration }};
}}

function classifyProximity(distFromPeak, trailPct) {{
    if (trailPct == null || distFromPeak == null) return 'normal';
    const gap = trailPct - distFromPeak; // how far from triggering the trail
    if (gap <= 0.5) return 'red';
    if (gap <= 1.0) return 'amber';
    return 'normal';
}}

function classifyBeta(beta) {{
    if (beta == null) return 'normal';
    const abs = Math.abs(beta);
    if (abs > 0.6) return 'red';
    if (abs > 0.4) return 'amber';
    return 'normal';
}}

function regimeColor(regime) {{
    if (!regime) return 'gray';
    switch (regime.toUpperCase()) {{
        case 'LEAN-IN': return 'green';
        case 'NEUTRAL': return 'gray';
        case 'CUT': return 'red';
        default: return 'gray';
    }}
}}

function computeConcentration(positions) {{
    const sectors = {{}};
    for (const pos of positions) {{
        const sector = pos.sector || HEDGE_TO_SECTOR[pos.hedge_ticker] || 'Unknown';
        if (!sectors[sector]) sectors[sector] = {{ count: 0, navPct: 0 }};
        sectors[sector].count += 1;
        sectors[sector].navPct += (pos.size_pct_nav || 0);
    }}
    // Classify each sector
    for (const [name, data] of Object.entries(sectors)) {{
        if (data.count >= 4) data.highlight = 'red';
        else if (data.count >= 3 || data.navPct > 0.12) data.highlight = 'amber';
        else data.highlight = 'normal';
    }}
    return sectors;
}}

function filterFactorDeltas(deltas) {{
    if (!deltas || typeof deltas !== 'object') return [];
    return Object.entries(deltas).filter(([key, val]) => Math.abs(val) > 0.1);
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
                <div class="chat-msg assistant">Desk assistant ready. Ask about positions, P&L, risk exposures, or trade recommendations.</div>
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
    overview: 'Jimothy Capital',
    pending: 'Trade Recommendations',
    positions: 'Portfolio Book',
    journal: 'Trade Blotter',
    debate: 'Investment Committee',
    risk: 'Risk Management',
    technical: 'Technical Analysis',
    calendar: 'Market Calendar',
    timeline: 'Run Log',
    chat: 'Desk Assistant',
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
