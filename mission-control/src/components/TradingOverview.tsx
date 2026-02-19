interface Props {
  balance: number;
  dailyPnl: number;
  totalTrades: number;
  maxBet: number;
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className="text-2xl font-bold text-gray-100 mt-1">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  );
}

export default function TradingOverview({ balance, dailyPnl, totalTrades, maxBet }: Props) {
  const pnlColor = dailyPnl > 0 ? 'text-green-400' : dailyPnl < 0 ? 'text-red-400' : 'text-gray-400';

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <StatCard label="Balance" value={`$${balance.toFixed(2)}`} />
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <div className="text-xs text-gray-500 uppercase tracking-wide">Daily PnL</div>
        <div className={`text-2xl font-bold mt-1 ${pnlColor}`}>
          {dailyPnl >= 0 ? '+' : ''}${dailyPnl.toFixed(2)}
        </div>
      </div>
      <StatCard label="Total Trades" value={String(totalTrades)} />
      <StatCard label="Max Bet" value={`$${maxBet}`} sub="current tier" />
    </div>
  );
}
