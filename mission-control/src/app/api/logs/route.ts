import { NextResponse } from 'next/server';
import db from '@/lib/db';

export const dynamic = 'force-dynamic';

export function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const source = searchParams.get('source') || 'trader.log';
  const limit = parseInt(searchParams.get('limit') || '200');

  const rows = db
    .prepare(
      `SELECT timestamp, source, level, message, raw, created_at
       FROM activity
       WHERE source = ?
       ORDER BY id DESC
       LIMIT ?`
    )
    .all(source, limit) as any[];

  return NextResponse.json({ logs: rows.reverse() });
}
