export interface LogEntry {
  timestamp: string; // ISO 8601
  source: string;
  level: string | null;
  agent: string | null;
  eventType: string | null;
  message: string;
  raw: string;
}

// [2026-02-15 14:01:17] Message text here
const LOCAL_TIME_RE = /^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+(.+)$/;

// [2026-02-15T04:01:23.065Z] [INFO] Message text here
const ISO_LEVEL_RE = /^\[(\d{4}-\d{2}-\d{2}T[\d:.]+Z)\]\s+\[(\w+)\]\s+(.+)$/;

// Agent name detection in message text
const AGENT_NAMES = ['elliot', 'trader', 'dev'];

function detectAgent(message: string, source: string): string | null {
  const lower = message.toLowerCase();
  for (const name of AGENT_NAMES) {
    if (lower.includes(name)) return name;
  }
  // Infer from source file context
  if (source === 'telegram.log') return null; // multi-agent
  return null;
}

export function parseLogLine(line: string, source: string): LogEntry | null {
  const trimmed = line.trim();
  if (!trimmed) return null;

  // Skip queue.log debug spam
  if (source === 'queue.log' && trimmed.includes('[DEBUG]') && trimmed.includes('message(s) in queue')) {
    return null;
  }

  // Try ISO format with level (queue.log, telegram.log)
  let match = ISO_LEVEL_RE.exec(trimmed);
  if (match) {
    const [, timestamp, level, message] = match;
    return {
      timestamp,
      source,
      level,
      agent: detectAgent(message, source),
      eventType: null,
      message,
      raw: trimmed,
    };
  }

  // Try local time format (daemon.log, heartbeat.log)
  match = LOCAL_TIME_RE.exec(trimmed);
  if (match) {
    const [, localTime, message] = match;
    // Convert local time to ISO (assume UTC for consistency)
    const timestamp = localTime.replace(' ', 'T') + 'Z';
    return {
      timestamp,
      source,
      level: 'INFO',
      agent: detectAgent(message, source),
      eventType: null,
      message,
      raw: trimmed,
    };
  }

  // Unparseable line — still ingest it
  return {
    timestamp: new Date().toISOString(),
    source,
    level: null,
    agent: null,
    eventType: null,
    message: trimmed,
    raw: trimmed,
  };
}

export function parseEventFile(content: string): LogEntry | null {
  try {
    const event = JSON.parse(content.trim());
    const timestamp = new Date(event.timestamp).toISOString();
    const agent = event.agentId || null;
    const eventType = event.type || 'unknown';

    // Build a human-readable message
    let message: string;
    switch (eventType) {
      case 'processor_start':
        message = `Queue processor started with agents: ${(event.agents || []).join(', ')}`;
        break;
      case 'message_received':
        message = `[${event.channel}] ${event.sender}: ${(event.message || '').slice(0, 200)}`;
        break;
      case 'agent_routed':
        message = `Routed to ${event.agentName} (${event.provider}/${event.model})`;
        break;
      case 'chain_step_start':
        message = `Chain step started: ${event.stepType || 'unknown'}`;
        break;
      case 'chain_step_done':
        message = `Chain step completed: ${event.stepType || 'unknown'}`;
        break;
      case 'response_ready': {
        const preview = (event.responseText || '').slice(0, 200);
        message = `Response ready (${event.responseLength} chars): ${preview}`;
        break;
      }
      default:
        message = `Event: ${eventType}`;
    }

    return {
      timestamp,
      source: 'event',
      level: null,
      agent,
      eventType,
      message,
      raw: content.trim(),
    };
  } catch {
    return null;
  }
}
