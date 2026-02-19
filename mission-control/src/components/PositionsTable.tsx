interface Position {
  market?: string;
  market_name?: string;
  side?: string;
  entry_price?: number;
  position_size?: number;
  cost_basis?: number;
  edge_pct?: number;
  entry_edge?: number;
  status?: string;
  current_price?: number;
  shares?: number;
}

interface Props {
  positions: Position[];
}

export default function PositionsTable({ positions }: Props) {
  if (positions.length === 0) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-2">Open Positions</h3>
        <p className="text-xs text-gray-600">No open positions</p>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
      <h3 className="text-sm font-semibold text-gray-300 px-4 py-3 border-b border-gray-800">
        Open Positions ({positions.length})
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left px-4 py-2">Market</th>
              <th className="text-left px-4 py-2">Side</th>
              <th className="text-right px-4 py-2">Entry</th>
              <th className="text-right px-4 py-2">Size</th>
              <th className="text-right px-4 py-2">Edge%</th>
              <th className="text-left px-4 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos, i) => {
              const market = pos.market || pos.market_name || '—';
              const edge = pos.edge_pct ?? pos.entry_edge;
              const size = pos.position_size ?? pos.cost_basis;
              const is2x =
                pos.entry_price && pos.current_price && pos.current_price >= 2 * pos.entry_price;
              return (
                <tr
                  key={i}
                  className={`border-b border-gray-800/50 ${is2x ? 'bg-yellow-400/10' : 'hover:bg-gray-800/50'}`}
                >
                  <td className="px-4 py-2 text-gray-300 max-w-[200px] truncate">
                    {market}
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={
                        pos.side?.includes('YES')
                          ? 'text-green-400'
                          : pos.side?.includes('NO')
                            ? 'text-red-400'
                            : 'text-gray-400'
                      }
                    >
                      {pos.side || '—'}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right text-gray-300">
                    {pos.entry_price != null ? `${(pos.entry_price * 100).toFixed(1)}c` : '—'}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-300">
                    {size != null ? `$${size}` : '—'}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-300">
                    {edge != null ? `${edge.toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-4 py-2 text-gray-400">{pos.status || 'OPEN'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
