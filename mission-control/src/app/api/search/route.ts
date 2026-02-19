import { NextRequest, NextResponse } from 'next/server';
import db from '@/lib/db';

export const dynamic = 'force-dynamic';

export function GET(req: NextRequest) {
  const params = req.nextUrl.searchParams;
  const q = params.get('q')?.trim();
  const source = params.get('source'); // logs | journals | files
  const limit = Math.min(parseInt(params.get('limit') || '50'), 200);

  if (!q) {
    return NextResponse.json({ results: [], total: 0 });
  }

  // FTS5 query — escape special characters
  const ftsQuery = q.replace(/['"]/g, '').split(/\s+/).map((w) => `"${w}"`).join(' ');

  try {
    let sql = `
      SELECT source, highlight(search_index, 1, '<mark>', '</mark>') AS content, timestamp,
             rank
      FROM search_index
      WHERE search_index MATCH ?
    `;
    const values: any[] = [ftsQuery];

    if (source === 'logs') {
      sql += ` AND source LIKE '%.log'`;
    } else if (source === 'journals') {
      sql += ` AND (source LIKE '%journal%' OR source LIKE '%.jsonl')`;
    } else if (source === 'files') {
      sql += ` AND source NOT LIKE '%.log' AND source NOT LIKE '%journal%'`;
    }

    sql += ` ORDER BY rank LIMIT ?`;
    values.push(limit);

    const rows = db.prepare(sql).all(...values) as any[];

    // Group by type
    const grouped: Record<string, any[]> = { logs: [], journals: [], files: [] };
    for (const row of rows) {
      const s = row.source as string;
      if (s.endsWith('.log')) {
        grouped.logs.push(row);
      } else if (s.includes('journal') || s.endsWith('.jsonl')) {
        grouped.journals.push(row);
      } else {
        grouped.files.push(row);
      }
    }

    return NextResponse.json({ results: grouped, total: rows.length });
  } catch (e: any) {
    return NextResponse.json({ results: { logs: [], journals: [], files: [] }, total: 0, error: e.message });
  }
}
