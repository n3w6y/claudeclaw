'use client';

import { useState } from 'react';

interface Result {
  source: string;
  content: string;
  timestamp: string;
}

interface GroupedResults {
  logs: Result[];
  journals: Result[];
  files: Result[];
}

interface Props {
  results: GroupedResults;
  total: number;
  query: string;
}

function ResultGroup({ title, results, query }: { title: string; results: Result[]; query: string }) {
  if (results.length === 0) return null;

  return (
    <div className="mb-6">
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide px-4 mb-2">
        {title} ({results.length})
      </h3>
      <div className="space-y-1">
        {results.map((result, i) => (
          <ResultRow key={`${result.source}-${i}`} result={result} query={query} />
        ))}
      </div>
    </div>
  );
}

function ResultRow({ result, query }: { result: Result; query: string }) {
  const [expanded, setExpanded] = useState(false);

  // Shorten path for display
  const displayPath = result.source.replace(/^\/home\/[^/]+\//, '~/');

  // Get preview — first ~200 chars with match highlighted
  const content = result.content || '';
  const lines = content.split('\n');

  // Find first line containing the query (case insensitive)
  const lowerQuery = query.toLowerCase();
  const matchIdx = lines.findIndex((l) => l.toLowerCase().includes(lowerQuery));
  const contextStart = Math.max(0, matchIdx - 1);
  const previewLines = matchIdx >= 0 ? lines.slice(contextStart, contextStart + 2) : lines.slice(0, 2);
  const expandedLines = matchIdx >= 0 ? lines.slice(Math.max(0, matchIdx - 1), matchIdx + 4) : lines.slice(0, 5);

  return (
    <div
      className="px-4 py-2 hover:bg-gray-900/50 cursor-pointer border-b border-gray-900/30"
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs text-blue-400 truncate max-w-[400px]">{displayPath}</span>
        <span className="text-[10px] text-gray-600">
          {result.timestamp?.replace('T', ' ').slice(0, 19)}
        </span>
      </div>
      <div className="text-xs text-gray-400 leading-relaxed">
        {(expanded ? expandedLines : previewLines).map((line, i) => (
          <div
            key={i}
            className="truncate"
            dangerouslySetInnerHTML={{
              __html: line
                // Preserve FTS5 <mark> tags: split on them, escape the rest
                .split(/(<mark>|<\/mark>)/)
                .map((part) =>
                  part === '<mark>'
                    ? '<mark class="bg-yellow-400/30 text-yellow-200 px-0.5 rounded">'
                    : part === '</mark>'
                      ? '</mark>'
                      : part.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                )
                .join(''),
            }}
          />
        ))}
      </div>
      {lines.length > 2 && (
        <div className="text-[10px] text-gray-600 mt-1">
          {expanded ? 'click to collapse' : `+${lines.length - 2} more lines`}
        </div>
      )}
    </div>
  );
}

export default function SearchResults({ results, total, query }: Props) {
  if (!query) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-600 text-sm">
        Enter a search query
      </div>
    );
  }

  if (total === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-600 text-sm">
        No results for &quot;{query}&quot;
      </div>
    );
  }

  return (
    <div className="py-3">
      <div className="px-4 mb-3 text-xs text-gray-500">{total} result(s)</div>
      <ResultGroup title="Logs" results={results.logs} query={query} />
      <ResultGroup title="Journals" results={results.journals} query={query} />
      <ResultGroup title="Agent Files" results={results.files} query={query} />
    </div>
  );
}
