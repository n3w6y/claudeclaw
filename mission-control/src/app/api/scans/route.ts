import { NextResponse } from 'next/server';
import db from '@/lib/db';

export const dynamic = 'force-dynamic';

export function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const scanId = searchParams.get('scan_id');
  const limit = parseInt(searchParams.get('limit') || '500');
  const qualified = searchParams.get('qualified'); // "1", "0", or null (all)

  // If scan_id specified, return details for that scan
  if (scanId) {
    let query = 'SELECT * FROM scan_details WHERE scan_id = ?';
    const params: any[] = [scanId];

    if (qualified === '1' || qualified === '0') {
      query += ' AND qualified = ?';
      params.push(parseInt(qualified));
    }

    query += ' ORDER BY edge DESC';
    const rows = db.prepare(query).all(...params);
    return NextResponse.json({ details: rows });
  }

  // Otherwise return scan summaries (grouped by scan_id)
  const scans = db.prepare(`
    SELECT
      scan_id,
      scan_timestamp,
      COUNT(*) as total_evaluated,
      SUM(CASE WHEN qualified = 1 THEN 1 ELSE 0 END) as total_qualified,
      SUM(CASE WHEN qualified = 0 THEN 1 ELSE 0 END) as total_rejected,
      MAX(edge) as best_edge,
      GROUP_CONCAT(DISTINCT city) as cities
    FROM scan_details
    GROUP BY scan_id
    ORDER BY scan_timestamp DESC
    LIMIT ?
  `).all(limit) as any[];

  return NextResponse.json({ scans });
}
