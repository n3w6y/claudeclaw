interface Trade {
  id: number;
  timestamp: string;
  market: string | null;
  city: string | null;
  side: string | null;
  amount: number | null;
  price: number | null;
  edge_pct: number | null;
  action: string | null;
  status: string | null;
  pnl: number | null;
  return_amount: number | null;
}

const STATUS_COLORS: Record<string, string> = {
  FILLED: 'bg-green-400/20 text-green-400',
  RESOLVED: 'bg-cyan-400/20 text-cyan-400',
  CLOSED: 'bg-cyan-400/20 text-cyan-400',
  PENDING: 'bg-yellow-400/20 text-yellow-400',
  CANCELLED: 'bg-gray-600/20 text-gray-500',
  FAILED: 'bg-red-400/20 text-red-400',
  HYPOTHETICAL: 'bg-gray-600/20 text-gray-500',
  PAPER: 'bg-blue-400/20 text-blue-400',
};

function pnlColor(value: number): string {
  if (value > 0) return 'text-green-400';
  if (value < 0) return 'text-red-400';
  return 'text-gray-400';
}

function formatDollar(value: number | null): string {
  if (value == null) return '—';
  return `$${value.toFixed(2)}`;
}

interface Props {
  trades: Trade[];
}

export default function TradeHistory({ trades }: Props) {
  if (trades.length === 0) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-2">Trade History</h3>
        <p className="text-xs text-gray-600">No trades recorded</p>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
      <h3 className="text-sm font-semibold text-gray-300 px-4 py-3 border-b border-gray-800">
        Trade History ({trades.length})
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left px-4 py-2">Time</th>
              <th className="text-left px-4 py-2">Market</th>
              <th className="text-left px-4 py-2">Side</th>
              <th className="text-right px-4 py-2">Cost</th>
              <th className="text-right px-4 py-2">Return</th>
              <th className="text-right px-4 py-2">Net</th>
              <th className="text-right px-4 py-2">%</th>
              <th className="text-left px-4 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade) => {
              const statusClass = STATUS_COLORS[trade.status || ''] || 'bg-gray-700/20 text-gray-400';
              const cost = trade.amount;
              const ret = trade.return_amount;
              const net = cost != null && ret != null ? ret - cost : trade.pnl;
              const pct = cost != null && cost > 0 && net != null
                ? (net / cost) * 100
                : null;

              return (
                <tr key={trade.id} className="border-b border-gray-800/50 hover:bg-gray-800/50">
                  <td className="px-4 py-2 text-gray-500 whitespace-nowrap">
                    {trade.timestamp.replace('T', ' ').slice(0, 16)}
                  </td>
                  <td className="px-4 py-2 text-gray-300 max-w-[200px] truncate">
                    {trade.market || trade.city || '—'}
                  </td>
                  <td className="px-4 py-2 text-gray-400 uppercase">
                    {trade.side || '—'}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-300">
                    {formatDollar(cost)}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-300">
                    {formatDollar(ret)}
                  </td>
                  <td className={`px-4 py-2 text-right font-medium ${net != null ? pnlColor(net) : 'text-gray-500'}`}>
                    {net != null ? `${net >= 0 ? '+' : ''}$${net.toFixed(2)}` : '—'}
                  </td>
                  <td className={`px-4 py-2 text-right font-medium ${pct != null ? pnlColor(pct) : 'text-gray-500'}`}>
                    {pct != null ? `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-4 py-2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${statusClass}`}>
                      {trade.status || 'UNKNOWN'}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
