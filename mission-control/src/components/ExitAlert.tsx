'use client';

import { useState, useEffect } from 'react';

interface Alert {
  market: string;
  entry_price: number;
  edge_pct: number;
}

interface Props {
  alerts: Alert[];
  onDismiss: (market: string) => void;
}

export default function ExitAlert({ alerts, onDismiss }: Props) {
  const [visible, setVisible] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const newVisible: Record<string, boolean> = {};
    for (const a of alerts) {
      newVisible[a.market] = true;
    }
    setVisible((prev) => ({ ...prev, ...newVisible }));
  }, [alerts]);

  const activeAlerts = alerts.filter((a) => visible[a.market]);

  if (activeAlerts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {activeAlerts.map((alert) => (
        <div
          key={alert.market}
          className="bg-yellow-900/90 border border-yellow-600 rounded-lg p-3 shadow-lg backdrop-blur-sm"
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-xs font-bold text-yellow-400 uppercase tracking-wide">
                2x Exit Trigger
              </div>
              <div className="text-sm text-yellow-100 mt-1 break-all">
                {alert.market}
              </div>
              <div className="text-xs text-yellow-300 mt-1">
                Edge: {alert.edge_pct.toFixed(1)}% | Entry: {(alert.entry_price * 100).toFixed(1)}c
              </div>
            </div>
            <button
              onClick={() => {
                setVisible((prev) => ({ ...prev, [alert.market]: false }));
                onDismiss(alert.market);
              }}
              className="text-yellow-500 hover:text-yellow-300 text-sm shrink-0"
            >
              x
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
