/**
 * Utility for the trader agent to write a standardized trading_state.json.
 * This is the single source of truth for the trading dashboard.
 *
 * Usage from trader agent:
 *   import { writeTradingState } from './write-trading-state';
 *   writeTradingState({ balance: 56.34, open_positions: [...], ... });
 *
 * Or call directly:
 *   npx tsx src/lib/write-trading-state.ts --balance 56.34 --trades 3 --pnl 0.37
 */

import fs from 'fs';
import path from 'path';
import os from 'os';

const STATE_PATH = path.join(
  os.homedir(),
  'claudeclaw', 'trader', 'polymarket-trader', 'trading_state.json'
);

export interface TradingStateContract {
  balance: number;
  open_positions: any[];
  open_orders: any[];
  total_trades: number;
  total_pnl: number;
  daily_pnl: number;
  trades_today: number;
  last_scan: string;
}

export function writeTradingState(state: TradingStateContract): void {
  const json = JSON.stringify(state, null, 2) + '\n';
  fs.mkdirSync(path.dirname(STATE_PATH), { recursive: true });
  fs.writeFileSync(STATE_PATH, json, 'utf-8');
}

export function readTradingState(): TradingStateContract | null {
  try {
    const content = fs.readFileSync(STATE_PATH, 'utf-8');
    return JSON.parse(content);
  } catch {
    return null;
  }
}

// CLI usage
if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.includes('--help') || args.length === 0) {
    console.log('Usage: npx tsx src/lib/write-trading-state.ts --balance 56.34 --trades 3 --pnl 0.37');
    console.log(`File: ${STATE_PATH}`);
    process.exit(0);
  }

  // Read current state as base
  const current = readTradingState() || {
    balance: 0, open_positions: [], open_orders: [], total_trades: 0,
    total_pnl: 0, daily_pnl: 0, trades_today: 0,
    last_scan: new Date().toISOString(),
  };

  // Apply CLI overrides
  for (let i = 0; i < args.length; i += 2) {
    const key = args[i]?.replace('--', '');
    const val = args[i + 1];
    if (!key || !val) continue;

    switch (key) {
      case 'balance': current.balance = parseFloat(val); break;
      case 'trades': current.total_trades = parseInt(val); break;
      case 'pnl': current.total_pnl = parseFloat(val); break;
      case 'daily-pnl': current.daily_pnl = parseFloat(val); break;
      case 'trades-today': current.trades_today = parseInt(val); break;
    }
  }

  current.last_scan = new Date().toISOString();
  writeTradingState(current);
  console.log(`Written to ${STATE_PATH}`);
  console.log(JSON.stringify(current, null, 2));
}
