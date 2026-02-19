import { NextRequest, NextResponse } from 'next/server';
import db from '@/lib/db';

export const dynamic = 'force-dynamic';

export function GET(req: NextRequest) {
  const params = req.nextUrl.searchParams;
  const limit = Math.min(parseInt(params.get('limit') || '200'), 1000);
  const offset = parseInt(params.get('offset') || '0');
  const agent = params.get('agent');
  const level = params.get('level');
  const after = params.get('after'); // id > after
  const q = params.get('q');

  const conditions: string[] = [];
  const values: any[] = [];

  if (agent) {
    conditions.push('agent = ?');
    values.push(agent);
  }
  if (level) {
    conditions.push('level = ?');
    values.push(level);
  }
  if (after) {
    conditions.push('id > ?');
    values.push(parseInt(after));
  }
  if (q) {
    conditions.push('message LIKE ?');
    values.push(`%${q}%`);
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

  const rows = db
    .prepare(
      `SELECT id, timestamp, source, level, agent, event_type, message
       FROM activity ${where}
       ORDER BY timestamp DESC, id DESC
       LIMIT ? OFFSET ?`
    )
    .all(...values, limit, offset);

  return NextResponse.json(rows);
}
