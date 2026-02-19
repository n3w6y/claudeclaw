'use client';

import { useCallback, useRef } from 'react';

const AGENTS = ['elliot', 'trader', 'dev'] as const;
const AGENT_COLORS: Record<string, string> = {
  elliot: 'accent-blue-400',
  trader: 'accent-green-400',
  dev: 'accent-purple-400',
};

interface Filters {
  agents: string[];
  keyword: string;
  level: string;
}

interface Props {
  filters: Filters;
  onChange: (filters: Filters) => void;
}

export default function FilterBar({ filters, onChange }: Props) {
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const handleKeyword = useCallback(
    (value: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        onChange({ ...filters, keyword: value });
      }, 300);
    },
    [filters, onChange]
  );

  const toggleAgent = useCallback(
    (agent: string) => {
      const agents = filters.agents.includes(agent)
        ? filters.agents.filter((a) => a !== agent)
        : [...filters.agents, agent];
      onChange({ ...filters, agents });
    },
    [filters, onChange]
  );

  return (
    <div className="flex flex-wrap items-center gap-3 px-3 py-2 bg-gray-900 border-b border-gray-800 text-xs">
      {AGENTS.map((agent) => (
        <label key={agent} className="flex items-center gap-1 cursor-pointer text-gray-400">
          <input
            type="checkbox"
            checked={filters.agents.includes(agent)}
            onChange={() => toggleAgent(agent)}
            className={`rounded ${AGENT_COLORS[agent]}`}
          />
          {agent}
        </label>
      ))}

      <select
        value={filters.level}
        onChange={(e) => onChange({ ...filters, level: e.target.value })}
        className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-300"
      >
        <option value="">all levels</option>
        <option value="ERROR">ERROR</option>
        <option value="WARN">WARN</option>
        <option value="INFO">INFO</option>
      </select>

      <input
        type="text"
        placeholder="filter..."
        defaultValue={filters.keyword}
        onChange={(e) => handleKeyword(e.target.value)}
        className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-300 placeholder-gray-600 flex-1 min-w-[120px]"
      />
    </div>
  );
}
