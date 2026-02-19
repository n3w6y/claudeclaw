import { redact } from '../secrets';

export interface TradingState {
  balance: number;
  totalTrades: number;
  totalPnl: number;
  dailyPnl: number;
  tradesToday: number;
  openPositionsJson: string;
  lastScan: string | null;
}

export function parseTradingState(content: string): TradingState | null {
  try {
    const data = JSON.parse(content);

    return {
      balance: data.balance ?? data.simulated_balance ?? 0,
      totalTrades: data.total_trades ?? 0,
      totalPnl: data.total_pnl ?? 0,
      dailyPnl: data.daily_pnl ?? 0,
      tradesToday: data.trades_today ?? 0,
      openPositionsJson: JSON.stringify(data.open_positions ?? []),
      lastScan: data.last_scan ?? null,
    };
  } catch {
    return null;
  }
}

// Standardised trading_state.json writer for the trader agent
export function buildTradingStateJson(state: {
  balance: number;
  open_positions: any[];
  total_trades: number;
  total_pnl: number;
  daily_pnl: number;
  trades_today: number;
  last_scan: string;
}): string {
  return JSON.stringify(state, null, 2);
}

export interface Position {
  timestamp: string;
  type: string;
  market: string;
  action: string;
  edge_pct: number;
  position_size: number;
  entry_price: number | null;
  status: string;
  venue: string;
}

export function parsePositions(json: string): Position[] {
  try {
    return JSON.parse(json) as Position[];
  } catch {
    return [];
  }
}

// Check if any position has hit 2x entry price (exit trigger)
export function checkExitTriggers(positions: Position[]): Position[] {
  return positions.filter((p) => {
    if (!p.entry_price || p.entry_price <= 0) return false;
    // A position hits 2x when current implied value >= 2 * entry_price
    // For prediction markets: if you bought YES at 0.30 and it's now at 0.60+, that's 2x
    // We flag positions where the edge suggests doubling
    return p.edge_pct >= 100;
  });
}
