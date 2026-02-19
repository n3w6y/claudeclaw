import { NextRequest } from 'next/server';
import db from '@/lib/db';

export const dynamic = 'force-dynamic';

export function GET(req: NextRequest) {
  let lastUpdatedAt = '';

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      const send = (event: string, data: any) => {
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      };

      send('connected', { ok: true });

      const poll = setInterval(() => {
        try {
          const state = db.prepare('SELECT * FROM trading_state LIMIT 1').get() as any;
          if (!state) return;

          if (state.updated_at !== lastUpdatedAt) {
            lastUpdatedAt = state.updated_at;

            const positions = JSON.parse(state.open_positions_json || '[]');
            const orders = JSON.parse(state.open_orders_json || '[]');

            send('state', {
              balance: state.balance,
              total_trades: state.total_trades,
              total_pnl: state.total_pnl,
              daily_pnl: state.daily_pnl,
              trades_today: state.trades_today,
              open_positions: positions,
              open_orders: orders,
              last_scan: state.last_scan,
              updated_at: state.updated_at,
            });

            // Check for 2x exit triggers
            for (const pos of positions) {
              if (pos.entry_price && pos.entry_price > 0 && pos.edge_pct >= 100) {
                send('exit_trigger', {
                  market: pos.market,
                  entry_price: pos.entry_price,
                  edge_pct: pos.edge_pct,
                });
              }
            }
          }
        } catch {
          // db temporarily locked
        }
      }, 5000);

      req.signal.addEventListener('abort', () => {
        clearInterval(poll);
        controller.close();
      });
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  });
}
