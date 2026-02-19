'use client';

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';

interface BalancePoint {
  timestamp: string;
  balance: number;
  event: string | null;
}

interface Props {
  balanceHistory: BalancePoint[];
}

export default function PnLChart({ balanceHistory }: Props) {
  if (balanceHistory.length === 0) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-2">Balance History</h3>
        <p className="text-xs text-gray-600">No balance data yet — watcher will record changes</p>
      </div>
    );
  }

  const startBalance = balanceHistory[0].balance;
  const data = balanceHistory.map((p) => ({
    date: p.timestamp.replace('T', ' ').slice(0, 16),
    balance: p.balance,
    pnl: Math.round((p.balance - startBalance) * 100) / 100,
  }));

  const currentPnl = data[data.length - 1].pnl;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-4">
        Balance History
        <span className={`ml-2 text-xs ${currentPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {currentPnl >= 0 ? '+' : ''}${currentPnl.toFixed(2)} PnL
        </span>
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data}>
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} />
          <YAxis
            tick={{ fontSize: 10, fill: '#6b7280' }}
            tickFormatter={(v) => `$${v}`}
            domain={['dataMin - 5', 'dataMax + 5']}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', fontSize: 12 }}
            labelStyle={{ color: '#9ca3af' }}
            formatter={(value: any) => [`$${Number(value).toFixed(2)}`, 'Balance']}
          />
          <ReferenceLine y={startBalance} stroke="#4b5563" strokeDasharray="3 3" />
          <Line
            type="monotone"
            dataKey="balance"
            stroke={currentPnl >= 0 ? '#4ade80' : '#f87171'}
            dot={false}
            strokeWidth={2}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
