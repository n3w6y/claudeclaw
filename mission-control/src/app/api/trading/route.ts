import { NextResponse } from 'next/server';
import db from '@/lib/db';

export const dynamic = 'force-dynamic';

// BET_TIERS from risk_manager.py — 5% of ceiling of each $100 range
function getMaxBet(balance: number): number {
  const tiers = [
    [0, 100, 5], [100, 200, 10], [200, 300, 15], [300, 400, 20],
    [400, 500, 25], [500, 600, 30], [600, 700, 35], [700, 800, 40],
    [800, 900, 45], [900, 1000, 50], [1000, Infinity, 55],
  ];
  for (const [lo, hi, bet] of tiers) {
    if (balance >= lo && balance < hi) return bet;
  }
  return 55;
}

export function GET() {
  const state = db.prepare('SELECT * FROM trading_state LIMIT 1').get() as any;
  const trades = db
    .prepare('SELECT * FROM trades ORDER BY timestamp DESC LIMIT 50')
    .all() as any[];
  const balanceHistory = db
    .prepare('SELECT timestamp, balance, event FROM balance_history ORDER BY timestamp ASC')
    .all() as any[];

  const balance = state?.balance ?? 0;

  return NextResponse.json({
    state: state
      ? {
          balance,
          total_trades: state.total_trades,
          total_pnl: state.total_pnl,
          daily_pnl: state.daily_pnl,
          trades_today: state.trades_today,
          open_positions: JSON.parse(state.open_positions_json || '[]'),
          open_orders: JSON.parse(state.open_orders_json || '[]'),
          last_scan: state.last_scan,
          updated_at: state.updated_at,
          max_bet: getMaxBet(balance),
        }
      : null,
    trades,
    balanceHistory,
  });
}
