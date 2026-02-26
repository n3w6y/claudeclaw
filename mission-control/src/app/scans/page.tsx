'use client';

import { useEffect, useState } from 'react';

interface ScanSummary {
  scan_id: string;
  scan_timestamp: string;
  total_evaluated: number;
  total_qualified: number;
  total_rejected: number;
  best_edge: number | null;
  cities: string;
}

interface ScanDetail {
  id: number;
  scan_id: string;
  scan_timestamp: string;
  city: string;
  market: string;
  side: string;
  edge: number;
  price: number;
  confidence: number;
  sources: string;
  forecast_temp: string;
  liquidity: number;
  rejection_reason: string | null;
  qualified: number;
}

const REJECTION_COLORS: Record<string, string> = {
  edge: 'text-orange-400',
  price: 'text-yellow-400',
  liquidity: 'text-red-400',
  source: 'text-purple-400',
  local: 'text-pink-400',
  duplicate: 'text-gray-500',
  opposing: 'text-gray-500',
  no_condition: 'text-gray-500',
};

function rejectionColor(reason: string): string {
  for (const [key, color] of Object.entries(REJECTION_COLORS)) {
    if (reason.toLowerCase().includes(key)) return color;
  }
  return 'text-gray-400';
}

export default function ScansPage() {
  const [scans, setScans] = useState<ScanSummary[]>([]);
  const [expandedScan, setExpandedScan] = useState<string | null>(null);
  const [details, setDetails] = useState<ScanDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [filter, setFilter] = useState<'all' | 'qualified' | 'rejected'>('all');

  useEffect(() => {
    fetch('/api/scans?limit=100')
      .then((r) => r.json())
      .then((data) => {
        setScans(data.scans || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // Poll for new scans every 30s
  useEffect(() => {
    const interval = setInterval(() => {
      fetch('/api/scans?limit=100')
        .then((r) => r.json())
        .then((data) => setScans(data.scans || []))
        .catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  function toggleScan(scanId: string) {
    if (expandedScan === scanId) {
      setExpandedScan(null);
      setDetails([]);
      return;
    }
    setExpandedScan(scanId);
    setDetailLoading(true);

    const qualParam = filter === 'qualified' ? '&qualified=1' : filter === 'rejected' ? '&qualified=0' : '';
    fetch(`/api/scans?scan_id=${encodeURIComponent(scanId)}${qualParam}`)
      .then((r) => r.json())
      .then((data) => {
        setDetails(data.details || []);
        setDetailLoading(false);
      })
      .catch(() => setDetailLoading(false));
  }

  // Re-fetch details when filter changes
  useEffect(() => {
    if (expandedScan) {
      setDetailLoading(true);
      const qualParam = filter === 'qualified' ? '&qualified=1' : filter === 'rejected' ? '&qualified=0' : '';
      fetch(`/api/scans?scan_id=${encodeURIComponent(expandedScan)}${qualParam}`)
        .then((r) => r.json())
        .then((data) => {
          setDetails(data.details || []);
          setDetailLoading(false);
        })
        .catch(() => setDetailLoading(false));
    }
  }, [filter, expandedScan]);

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800 bg-gray-900/80 backdrop-blur">
        <h2 className="text-sm font-semibold text-gray-300">Scan Details</h2>
        <span className="text-xs text-gray-600">{scans.length} scans</span>
        <div className="ml-auto flex gap-1">
          {(['all', 'qualified', 'rejected'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2 py-1 text-xs rounded transition-colors ${
                filter === f
                  ? f === 'qualified' ? 'bg-green-400/20 text-green-400'
                    : f === 'rejected' ? 'bg-red-400/20 text-red-400'
                    : 'bg-blue-400/20 text-blue-400'
                  : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <p className="text-gray-600 p-4 text-xs">Loading...</p>
        ) : scans.length === 0 ? (
          <div className="p-4">
            <p className="text-gray-600 text-xs">No scan data yet.</p>
            <p className="text-gray-700 text-xs mt-1">
              Scan details will appear here once the trader runs its next scan cycle.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-gray-800/50">
            {scans.map((scan) => (
              <div key={scan.scan_id}>
                {/* Scan summary row */}
                <button
                  onClick={() => toggleScan(scan.scan_id)}
                  className="w-full text-left px-4 py-3 hover:bg-gray-800/50 transition-colors flex items-center gap-4 text-xs"
                >
                  <span className="text-gray-500 w-36 shrink-0">
                    {scan.scan_timestamp.replace('T', ' ').slice(0, 19)}
                  </span>
                  <span className="text-gray-300">
                    {scan.total_evaluated} evaluated
                  </span>
                  {scan.total_qualified > 0 && (
                    <span className="text-green-400">
                      {scan.total_qualified} qualified
                    </span>
                  )}
                  <span className="text-red-400/70">
                    {scan.total_rejected} rejected
                  </span>
                  {scan.best_edge != null && (
                    <span className="text-gray-400">
                      best: {scan.best_edge.toFixed(1)}%
                    </span>
                  )}
                  <span className="text-gray-600 truncate ml-auto max-w-[200px]">
                    {scan.cities}
                  </span>
                  <span className="text-gray-600">
                    {expandedScan === scan.scan_id ? '▾' : '▸'}
                  </span>
                </button>

                {/* Expanded detail rows */}
                {expandedScan === scan.scan_id && (
                  <div className="bg-gray-900/50 border-t border-gray-800/50">
                    {detailLoading ? (
                      <p className="text-gray-600 p-4 text-xs">Loading details...</p>
                    ) : details.length === 0 ? (
                      <p className="text-gray-600 p-4 text-xs">No entries match filter.</p>
                    ) : (
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="text-gray-600 border-b border-gray-800/50">
                            <th className="text-left px-4 py-1.5">City</th>
                            <th className="text-left px-2 py-1.5">Side</th>
                            <th className="text-right px-2 py-1.5">Edge</th>
                            <th className="text-right px-2 py-1.5">Price</th>
                            <th className="text-right px-2 py-1.5">Conf</th>
                            <th className="text-left px-2 py-1.5">Sources</th>
                            <th className="text-left px-2 py-1.5">Temp</th>
                            <th className="text-right px-2 py-1.5">Liq</th>
                            <th className="text-left px-4 py-1.5">Result</th>
                          </tr>
                        </thead>
                        <tbody>
                          {details.map((d) => (
                            <tr
                              key={d.id}
                              className={`border-b border-gray-800/30 hover:bg-gray-800/30 ${
                                d.qualified ? 'bg-green-400/5' : ''
                              }`}
                            >
                              <td className="px-4 py-1.5 text-gray-300">{d.city}</td>
                              <td className="px-2 py-1.5 text-gray-400">{d.side}</td>
                              <td className={`px-2 py-1.5 text-right ${
                                d.edge >= 20 ? 'text-green-400' : 'text-orange-400'
                              }`}>
                                {d.edge.toFixed(1)}%
                              </td>
                              <td className="px-2 py-1.5 text-right text-gray-300">
                                {(d.price * 100).toFixed(1)}¢
                              </td>
                              <td className="px-2 py-1.5 text-right text-gray-400">
                                {(d.confidence * 100).toFixed(0)}%
                              </td>
                              <td className="px-2 py-1.5 text-gray-500">{d.sources}</td>
                              <td className="px-2 py-1.5 text-gray-500">{d.forecast_temp}</td>
                              <td className="px-2 py-1.5 text-right text-gray-500">
                                ${d.liquidity.toLocaleString()}
                              </td>
                              <td className="px-4 py-1.5">
                                {d.qualified ? (
                                  <span className="text-green-400 font-medium">QUALIFIED</span>
                                ) : (
                                  <span className={rejectionColor(d.rejection_reason || '')}>
                                    {d.rejection_reason}
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
