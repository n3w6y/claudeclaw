'use client';

import { useState, useEffect, useCallback } from 'react';
import TradingOverview from '@/components/TradingOverview';
import PositionsTable from '@/components/PositionsTable';
import OpenOrdersTable from '@/components/OpenOrdersTable';
import TradeHistory from '@/components/TradeHistory';
import PnLChart from '@/components/PnLChart';
import ExitAlert from '@/components/ExitAlert';

interface TradingState {
  balance: number;
  total_trades: number;
  total_pnl: number;
  daily_pnl: number;
  trades_today: number;
  open_positions: any[];
  open_orders: any[];
  last_scan: string | null;
  updated_at: string;
  max_bet: number;
}

interface ExitTrigger {
  market: string;
  entry_price: number;
  edge_pct: number;
}

export default function TradingPage() {
  const [state, setState] = useState<TradingState | null>(null);
  const [trades, setTrades] = useState<any[]>([]);
  const [balanceHistory, setBalanceHistory] = useState<any[]>([]);
  const [exitAlerts, setExitAlerts] = useState<ExitTrigger[]>([]);
  const [connected, setConnected] = useState(false);

  // Initial load
  useEffect(() => {
    fetch('/api/trading')
      .then((r) => r.json())
      .then((data) => {
        setState(data.state);
        setTrades(data.trades);
        setBalanceHistory(data.balanceHistory || []);
      });
  }, []);

  // SSE connection
  useEffect(() => {
    let es: EventSource | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout>;

    function connect() {
      es = new EventSource('/api/trading/stream');

      es.addEventListener('connected', () => setConnected(true));

      es.addEventListener('state', (event) => {
        const data = JSON.parse(event.data);
        setState((prev) => (prev ? { ...prev, ...data } : data));
      });

      es.addEventListener('exit_trigger', (event) => {
        const trigger = JSON.parse(event.data) as ExitTrigger;
        setExitAlerts((prev) => {
          if (prev.some((a) => a.market === trigger.market)) return prev;
          return [...prev, trigger];
        });
      });

      es.onerror = () => {
        setConnected(false);
        es?.close();
        reconnectTimeout = setTimeout(connect, 5000);
      };
    }

    connect();
    return () => {
      es?.close();
      clearTimeout(reconnectTimeout);
    };
  }, []);

  const dismissAlert = useCallback((market: string) => {
    setExitAlerts((prev) => prev.filter((a) => a.market !== market));
  }, []);

  if (!state) {
    return (
      <div className="flex items-center justify-center h-screen text-gray-600 text-sm">
        Loading trading data...
      </div>
    );
  }

  return (
    <div className="h-screen overflow-y-auto">
      <div className="p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-200">Trading Dashboard</h2>
          <div className="flex items-center gap-2 text-xs">
            {state.last_scan && (
              <span className="text-gray-500">
                last scan: {state.last_scan.replace('T', ' ').slice(0, 19)}
              </span>
            )}
            <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'}`} />
          </div>
        </div>

        <TradingOverview
          balance={state.balance}
          dailyPnl={state.daily_pnl}
          totalTrades={state.total_trades}
          maxBet={state.max_bet}
        />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <PositionsTable positions={state.open_positions} />
          <OpenOrdersTable orders={state.open_orders} />
        </div>

        <PnLChart balanceHistory={balanceHistory} />
        <TradeHistory trades={trades} />
      </div>

      <ExitAlert alerts={exitAlerts} onDismiss={dismissAlert} />
    </div>
  );
}
