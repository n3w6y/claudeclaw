'use client';

import { useState, useEffect } from 'react';

interface Order {
  order_id?: string;
  market?: string;
  side?: string;
  price?: number;
  amount?: number;
  time_placed?: string;
  TTL_expiry?: string;
}

interface Props {
  orders: Order[];
}

function formatRemaining(expiryStr?: string): { text: string; urgent: boolean } {
  if (!expiryStr) return { text: '—', urgent: false };
  const remaining = new Date(expiryStr).getTime() - Date.now();
  if (remaining <= 0) return { text: 'EXPIRED', urgent: true };
  const mins = Math.floor(remaining / 60000);
  const secs = Math.floor((remaining % 60000) / 1000);
  return {
    text: `${mins}m ${secs}s`,
    urgent: remaining < 5 * 60000,
  };
}

export default function OpenOrdersTable({ orders }: Props) {
  const [, setTick] = useState(0);

  // Re-render every second for TTL countdown
  useEffect(() => {
    if (orders.length === 0) return;
    const interval = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(interval);
  }, [orders.length]);

  if (orders.length === 0) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-2">Open Orders</h3>
        <p className="text-xs text-gray-600">No pending orders</p>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
      <h3 className="text-sm font-semibold text-gray-300 px-4 py-3 border-b border-gray-800">
        Open Orders ({orders.length})
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left px-4 py-2">Market</th>
              <th className="text-left px-4 py-2">Side</th>
              <th className="text-right px-4 py-2">Price</th>
              <th className="text-right px-4 py-2">Amount</th>
              <th className="text-left px-4 py-2">Placed</th>
              <th className="text-right px-4 py-2">TTL</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order, i) => {
              const ttl = formatRemaining(order.TTL_expiry);
              return (
                <tr
                  key={order.order_id || i}
                  className={`border-b border-gray-800/50 ${ttl.urgent ? 'bg-orange-400/10' : 'hover:bg-gray-800/50'}`}
                >
                  <td className="px-4 py-2 text-gray-300 max-w-[200px] truncate">
                    {order.market || '—'}
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={
                        order.side?.includes('YES')
                          ? 'text-green-400'
                          : order.side?.includes('NO')
                            ? 'text-red-400'
                            : 'text-gray-400'
                      }
                    >
                      {order.side || '—'}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right text-gray-300">
                    {order.price != null ? `${(order.price * 100).toFixed(1)}c` : '—'}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-300">
                    {order.amount != null ? `$${order.amount}` : '—'}
                  </td>
                  <td className="px-4 py-2 text-gray-400">
                    {order.time_placed
                      ? order.time_placed.replace('T', ' ').slice(0, 19)
                      : '—'}
                  </td>
                  <td className={`px-4 py-2 text-right ${ttl.urgent ? 'text-orange-400 font-bold' : 'text-gray-400'}`}>
                    {ttl.text}
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
