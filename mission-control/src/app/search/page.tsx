'use client';

import { useState, useCallback } from 'react';
import SearchBar from '@/components/SearchBar';
import SearchResults from '@/components/SearchResults';

interface GroupedResults {
  logs: any[];
  journals: any[];
  files: any[];
}

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('');
  const [results, setResults] = useState<GroupedResults>({ logs: [], journals: [], files: [] });
  const [total, setTotal] = useState(0);
  const [searchedQuery, setSearchedQuery] = useState('');
  const [loading, setLoading] = useState(false);

  const doSearch = useCallback(async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ q: query.trim() });
      if (source) params.set('source', source);
      const res = await fetch(`/api/search?${params}`);
      const data = await res.json();
      setResults(data.results);
      setTotal(data.total);
      setSearchedQuery(query.trim());
    } finally {
      setLoading(false);
    }
  }, [query, source]);

  return (
    <div className="h-screen flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800">
        <h2 className="text-sm font-semibold text-gray-200">Global Search</h2>
      </div>
      <SearchBar
        value={query}
        onChange={setQuery}
        onSubmit={doSearch}
        source={source}
        onSourceChange={setSource}
      />
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center h-64 text-gray-600 text-sm">
            Searching...
          </div>
        ) : (
          <SearchResults results={results} total={total} query={searchedQuery} />
        )}
      </div>
    </div>
  );
}
