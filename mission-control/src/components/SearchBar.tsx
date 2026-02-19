'use client';

import { useRef, useEffect } from 'react';

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  source: string;
  onSourceChange: (source: string) => void;
}

export default function SearchBar({ value, onChange, onSubmit, source, onSourceChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);

  // Cmd+K to focus
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);

  return (
    <div className="flex flex-wrap items-center gap-2 px-4 py-3 bg-gray-900 border-b border-gray-800">
      <div className="flex-1 min-w-[200px] relative">
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onSubmit()}
          placeholder="Search... (Ctrl+K)"
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-500"
        />
        <kbd className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-gray-600 bg-gray-700 px-1.5 py-0.5 rounded hidden sm:inline">
          Ctrl+K
        </kbd>
      </div>

      <select
        value={source}
        onChange={(e) => onSourceChange(e.target.value)}
        className="bg-gray-800 border border-gray-700 rounded px-2 py-2 text-xs text-gray-300"
      >
        <option value="">All sources</option>
        <option value="logs">Logs</option>
        <option value="journals">Journals</option>
        <option value="files">Agent Files</option>
      </select>

      <button
        onClick={onSubmit}
        className="bg-blue-600 hover:bg-blue-500 text-white text-xs px-4 py-2 rounded transition-colors"
      >
        Search
      </button>
    </div>
  );
}
