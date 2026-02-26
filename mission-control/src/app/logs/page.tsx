'use client';

import { useEffect, useState, useRef } from 'react';

interface LogEntry {
  timestamp: string;
  source: string;
  level: string | null;
  message: string;
  raw: string | null;
}

const SOURCES = [
  'trader.log',
  'daemon.log',
  'queue.log',
  'telegram.log',
  'heartbeat.log',
];

const LEVEL_COLORS: Record<string, string> = {
  ERROR: 'text-red-400',
  WARN: 'text-yellow-400',
  WARNING: 'text-yellow-400',
  INFO: 'text-gray-400',
  DEBUG: 'text-gray-600',
};

export default function LogsPage() {
  const [source, setSource] = useState('trader.log');
  const [limit, setLimit] = useState(300);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/logs?source=${encodeURIComponent(source)}&limit=${limit}`)
      .then((r) => r.json())
      .then((data) => {
        setLogs(data.logs || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [source, limit]);

  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  // Poll for new entries every 3s
  useEffect(() => {
    const interval = setInterval(() => {
      fetch(`/api/logs?source=${encodeURIComponent(source)}&limit=${limit}`)
        .then((r) => r.json())
        .then((data) => setLogs(data.logs || []))
        .catch(() => {});
    }, 3000);
    return () => clearInterval(interval);
  }, [source, limit]);

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800 bg-gray-900/80 backdrop-blur">
        <h2 className="text-sm font-semibold text-gray-300">Logs</h2>
        <div className="flex gap-1">
          {SOURCES.map((s) => (
            <button
              key={s}
              onClick={() => setSource(s)}
              className={`px-2 py-1 text-xs rounded transition-colors ${
                source === s
                  ? 'bg-blue-400/20 text-blue-400'
                  : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'
              }`}
            >
              {s.replace('.log', '')}
            </button>
          ))}
        </div>
        <select
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
          className="ml-auto text-xs bg-gray-800 border border-gray-700 text-gray-300 rounded px-2 py-1"
        >
          <option value={100}>100 lines</option>
          <option value={300}>300 lines</option>
          <option value={1000}>1000 lines</option>
        </select>
        <button
          onClick={() => setAutoScroll(!autoScroll)}
          className={`text-xs px-2 py-1 rounded ${
            autoScroll ? 'bg-green-400/20 text-green-400' : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          {autoScroll ? 'auto-scroll on' : 'auto-scroll off'}
        </button>
      </div>

      {/* Log output */}
      <div className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-relaxed">
        {loading ? (
          <p className="text-gray-600">Loading...</p>
        ) : logs.length === 0 ? (
          <p className="text-gray-600">No logs for {source}</p>
        ) : (
          logs.map((entry, i) => {
            const levelClass = LEVEL_COLORS[entry.level?.toUpperCase() || ''] || 'text-gray-400';
            return (
              <div key={i} className="hover:bg-gray-800/50 py-0.5">
                <span className="text-gray-600">
                  {entry.timestamp?.replace('T', ' ').replace('Z', '').slice(0, 19)}
                </span>{' '}
                {entry.level && (
                  <span className={levelClass}>[{entry.level}]</span>
                )}{' '}
                <span className="text-gray-300">{entry.message}</span>
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
