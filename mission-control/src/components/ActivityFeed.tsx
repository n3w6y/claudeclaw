'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import ActivityEntry from './ActivityEntry';
import FilterBar from './FilterBar';

interface Entry {
  id: number;
  timestamp: string;
  source: string;
  level: string | null;
  agent: string | null;
  event_type: string | null;
  message: string;
}

interface Filters {
  agents: string[];
  keyword: string;
  level: string;
}

export default function ActivityFeed() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [filters, setFilters] = useState<Filters>({ agents: [], keyword: '', level: '' });
  const [autoScroll, setAutoScroll] = useState(true);
  const [connected, setConnected] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastIdRef = useRef(0);

  // Initial load
  useEffect(() => {
    fetch('/api/activity?limit=200')
      .then((r) => r.json())
      .then((rows: Entry[]) => {
        // API returns timestamp DESC — reverse to chronological, then track max id
        const sorted = [...rows].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
        setEntries(sorted);
        if (rows.length > 0) {
          lastIdRef.current = Math.max(...rows.map((r) => r.id));
        }
      });
  }, []);

  // SSE connection
  useEffect(() => {
    let es: EventSource | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout>;

    function connect() {
      es = new EventSource(`/api/activity/stream?lastId=${lastIdRef.current}`);

      es.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'connected') {
          setConnected(true);
          return;
        }
        if (msg.type === 'entries' && msg.data) {
          const newEntries = msg.data as Entry[];
          if (newEntries.length > 0) {
            lastIdRef.current = Math.max(...newEntries.map((e) => e.id));
            setEntries((prev) => {
              const merged = [...prev, ...newEntries];
              merged.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
              return merged;
            });
          }
        }
      };

      es.onerror = () => {
        setConnected(false);
        es?.close();
        reconnectTimeout = setTimeout(connect, 5000);
      };
    }

    connect();

    return () => {
      es?.close();
      clearTimeout(reconnectTimeout);
    };
  }, []);

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries, autoScroll]);

  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const nearBottom = scrollHeight - scrollTop - clientHeight < 80;
    setAutoScroll(nearBottom);
  }, []);

  // Apply filters client-side
  const filtered = entries.filter((e) => {
    if (filters.agents.length > 0 && (!e.agent || !filters.agents.includes(e.agent))) return false;
    if (filters.level && e.level !== filters.level) return false;
    if (filters.keyword && !e.message.toLowerCase().includes(filters.keyword.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800">
        <h2 className="text-sm font-semibold text-gray-200">Activity Feed</h2>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-gray-500">{filtered.length} entries</span>
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'}`} />
        </div>
      </div>
      <FilterBar filters={filters} onChange={setFilters} />
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
      >
        {filtered.map((entry) => (
          <ActivityEntry key={entry.id} entry={entry} />
        ))}
        {filtered.length === 0 && (
          <div className="flex items-center justify-center h-32 text-gray-600 text-sm">
            No activity entries
          </div>
        )}
      </div>
      {!autoScroll && (
        <button
          onClick={() => {
            setAutoScroll(true);
            if (scrollRef.current) {
              scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
            }
          }}
          className="absolute bottom-4 right-4 bg-gray-800 border border-gray-700 rounded-full px-3 py-1 text-xs text-gray-300 hover:text-gray-100 shadow-lg"
        >
          scroll to bottom
        </button>
      )}
    </div>
  );
}
