import { NextRequest } from 'next/server';
import db from '@/lib/db';

export const dynamic = 'force-dynamic';

export function GET(req: NextRequest) {
  const params = req.nextUrl.searchParams;
  let lastId = parseInt(params.get('lastId') || '0');

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      const send = (data: string) => {
        controller.enqueue(encoder.encode(`data: ${data}\n\n`));
      };

      // Send heartbeat immediately
      send(JSON.stringify({ type: 'connected' }));

      const poll = setInterval(() => {
        try {
          const rows = db
            .prepare(
              `SELECT id, timestamp, source, level, agent, event_type, message
               FROM activity WHERE id > ? ORDER BY timestamp ASC, id ASC LIMIT 50`
            )
            .all(lastId) as any[];

          if (rows.length > 0) {
            // Track highest id for pagination, but send sorted by timestamp
            lastId = Math.max(...rows.map((r: any) => r.id));
            send(JSON.stringify({ type: 'entries', data: rows }));
          }
        } catch {
          // db might be temporarily locked
        }
      }, 2000);

      // Clean up when client disconnects
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
