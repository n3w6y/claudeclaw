const AGENT_COLORS: Record<string, string> = {
  elliot: 'bg-blue-400/20 text-blue-400',
  trader: 'bg-green-400/20 text-green-400',
  dev: 'bg-purple-400/20 text-purple-400',
};

const LEVEL_COLORS: Record<string, string> = {
  ERROR: 'text-red-400',
  WARN: 'text-yellow-400',
  INFO: 'text-gray-400',
  DEBUG: 'text-gray-600',
};

interface Props {
  entry: {
    id: number;
    timestamp: string;
    source: string;
    level: string | null;
    agent: string | null;
    event_type: string | null;
    message: string;
  };
}

export default function ActivityEntry({ entry }: Props) {
  const time = entry.timestamp.replace('T', ' ').replace('Z', '').slice(0, 19);
  const agentClass = entry.agent ? AGENT_COLORS[entry.agent] : null;
  const levelClass = entry.level ? LEVEL_COLORS[entry.level] || 'text-gray-500' : null;

  return (
    <div className="flex items-start gap-2 px-3 py-1 hover:bg-gray-900/50 text-xs leading-5 border-b border-gray-900/50">
      <span className="text-gray-600 shrink-0 w-[130px]">{time}</span>
      {entry.agent && agentClass && (
        <span className={`shrink-0 px-1.5 py-0 rounded text-[10px] font-medium ${agentClass}`}>
          {entry.agent}
        </span>
      )}
      {entry.level && levelClass && (
        <span className={`shrink-0 text-[10px] font-medium w-10 ${levelClass}`}>
          {entry.level}
        </span>
      )}
      <span className="text-gray-300 break-all min-w-0">{entry.message}</span>
    </div>
  );
}
