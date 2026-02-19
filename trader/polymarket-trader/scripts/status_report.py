#!/usr/bin/env python3
"""
Generate status report for paper trading trial.
Outputs summary suitable for Telegram message.
"""

import json
from datetime import datetime
from pathlib import Path
from collections import defaultdict

SCRIPT_DIR = Path(__file__).parent
CONFIG_DIR = SCRIPT_DIR.parent / "config"
JOURNAL_DIR = SCRIPT_DIR.parent / "journal"

STATE_FILE = CONFIG_DIR / "trading_state.json"
PAPER_TRADE_LOG = JOURNAL_DIR / "paper_trades.jsonl"
HYPOTHETICAL_LOG = JOURNAL_DIR / "hypothetical_trades.jsonl"
SCAN_LOG = JOURNAL_DIR / "scan_log.jsonl"

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def load_jsonl(filepath):
    if not filepath.exists():
        return []
    with open(filepath) as f:
        return [json.loads(line) for line in f if line.strip()]

def generate_report():
    state = load_state()
    paper_trades = load_jsonl(PAPER_TRADE_LOG)
    hypotheticals = load_jsonl(HYPOTHETICAL_LOG)
    scans = load_jsonl(SCAN_LOG)
    
    now = datetime.now()
    
    # Trial timing
    trial_start = datetime.fromisoformat(state.get("trial_start", now.isoformat()))
    trial_end = datetime.fromisoformat(state.get("trial_end", now.isoformat()))
    elapsed = (now - trial_start).total_seconds() / 3600
    remaining = max(0, (trial_end - now).total_seconds() / 3600)
    
    # Group trades by market
    markets = defaultdict(list)
    for trade in paper_trades:
        market = trade.get("market", "Unknown")[:40]
        markets[market].append(trade)
    
    # Build report
    lines = []
    lines.append("📊 *Polymarket Paper Trading Update*")
    lines.append(f"⏱ {elapsed:.1f}h elapsed | {remaining:.1f}h remaining")
    lines.append("")
    
    # Overview
    lines.append(f"💰 Simulated Balance: ${state.get('simulated_balance', 100):.2f}")
    lines.append(f"📈 Total Trades: {len(paper_trades)}")
    lines.append(f"📝 Hypotheticals Logged: {len(hypotheticals)}")
    lines.append(f"🔍 Scans Completed: {len(scans)}")
    lines.append("")
    
    # Trades by market
    if markets:
        lines.append("*Positions by Market:*")
        for market, trades in sorted(markets.items(), key=lambda x: -len(x[1]))[:5]:
            edges = [t.get("edge_pct", 0) for t in trades]
            avg_edge = sum(edges) / len(edges) if edges else 0
            total_size = sum(t.get("position_size", 0) for t in trades)
            lines.append(f"• {market}...")
            lines.append(f"  {len(trades)} trades | ${total_size:.2f} | {avg_edge:.1f}% avg edge")
        lines.append("")
    
    # Recent activity
    if paper_trades:
        recent = paper_trades[-3:]
        lines.append("*Recent Trades:*")
        for t in recent:
            ts = t.get("timestamp", "")[:16]
            market = t.get("market", "")[:30]
            edge = t.get("edge_pct", 0)
            lines.append(f"• {ts} - {market}... @ {edge:.1f}%")
        lines.append("")
    
    # Weather hypotheticals
    if hypotheticals:
        lines.append(f"*Weather Hypotheticals:* {len(hypotheticals)}")
        for h in hypotheticals[-2:]:
            city = h.get("city", "Unknown")
            edge = h.get("edge_pct", 0)
            action = h.get("action", "")
            lines.append(f"• {city}: {action} @ {edge:.1f}% edge")
        lines.append("")
    
    # Status
    if remaining > 0:
        lines.append("🟢 Trial in progress...")
    else:
        lines.append("✅ Trial complete! Ready for review.")
    
    return "\n".join(lines)

if __name__ == "__main__":
    print(generate_report())
