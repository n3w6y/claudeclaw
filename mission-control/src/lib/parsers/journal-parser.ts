export interface TradeEntry {
  timestamp: string;
  sourceFile: string;
  market: string | null;
  city: string | null;
  side: string | null;
  amount: number | null;
  price: number | null;
  edgePct: number | null;
  confidence: number | null;
  action: string | null;
  status: string;
  pnl: number | null;
  orderId: string | null;
  url: string | null;
  raw: string;
}

export function parseJsonlTrade(line: string, sourceFile: string): TradeEntry | null {
  try {
    const data = JSON.parse(line.trim());
    if (!data.timestamp) return null;

    // Determine status from source file and data
    let status = 'UNKNOWN';
    if (sourceFile.includes('hypothetical')) {
      status = 'HYPOTHETICAL';
    } else if (sourceFile.includes('paper')) {
      status = data.status || 'PAPER';
    } else {
      status = data.status || 'EXECUTED';
    }

    return {
      timestamp: data.timestamp,
      sourceFile,
      market: data.market || data.question || null,
      city: data.city || null,
      side: data.side || null,
      amount: data.position_size || data.amount || data.hypothetical_size || null,
      price: data.entry_price || data.market_yes_price || data.price || null,
      edgePct: data.edge_pct || data.adjusted_edge_pct || null,
      confidence: data.forecast_confidence || data.confidence || null,
      action: data.action || null,
      status,
      pnl: data.pnl || null,
      orderId: data.order_id || null,
      url: data.url || null,
      raw: line.trim(),
    };
  } catch {
    return null;
  }
}

// Parse markdown journal entries (trade sections)
export function parseMarkdownTrades(content: string, sourceFile: string): TradeEntry[] {
  const trades: TradeEntry[] = [];
  const sections = content.split(/^### Trade @/m);

  for (const section of sections.slice(1)) {
    const lines = section.split('\n');
    const timestampMatch = lines[0]?.match(/(\d{4}-\d{2}-\d{2}T[\d:]+)/);
    if (!timestampMatch) continue;

    const fields: Record<string, string> = {};
    for (const line of lines) {
      const m = line.match(/^\s*-\s+\*\*(\w+):\*\*\s+(.+)$/);
      if (m) fields[m[1].toLowerCase()] = m[2].trim();
    }

    trades.push({
      timestamp: timestampMatch[1],
      sourceFile,
      market: fields.market || null,
      city: null,
      side: fields.side || null,
      amount: fields.amount ? parseFloat(fields.amount.replace('$', '')) : null,
      price: fields.price ? parseFloat(fields.price.replace('%', '')) / 100 : null,
      edgePct: null,
      confidence: null,
      action: fields.side ? `BUY ${fields.side}` : null,
      status: fields.outcome === '*pending*' ? 'PENDING' : (fields.outcome || 'UNKNOWN'),
      pnl: null,
      orderId: null,
      url: null,
      raw: `### Trade @${section.slice(0, 500)}`,
    });
  }

  return trades;
}
