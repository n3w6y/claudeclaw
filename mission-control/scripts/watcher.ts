#!/usr/bin/env tsx
/**
 * Mission Control File Watcher
 *
 * Long-running process that tails log files, ingests events, and updates
 * trading state into SQLite. Runs as a separate systemd service.
 *
 * Usage: npx tsx scripts/watcher.ts
 */

import Database from 'better-sqlite3';
import fs from 'fs';
import path from 'path';
import os from 'os';

// ============================================================================
// Paths (duplicated from src/lib/paths.ts to avoid Next.js import issues)
// ============================================================================
const HOME = os.homedir();
const DB_PATH = path.join(HOME, 'claudeclaw', 'mission-control', 'data.db');
const TINYCLAW_LOGS_DIR = path.join(HOME, '.tinyclaw', 'logs');
const TINYCLAW_EVENTS_DIR = path.join(HOME, '.tinyclaw', 'events');
const TRADER_BASE = path.join(HOME, 'claudeclaw', 'trader', 'polymarket-trader');
const TRADING_STATE_FILE = path.join(TRADER_BASE, 'trading_state.json');
const OPEN_ORDERS_FILE = path.join(TRADER_BASE, 'open_orders.json');
const JOURNAL_DIR = path.join(TRADER_BASE, 'journal');

const LOG_FILES = [
  { path: path.join(TINYCLAW_LOGS_DIR, 'daemon.log'), source: 'daemon.log' },
  { path: path.join(TINYCLAW_LOGS_DIR, 'queue.log'), source: 'queue.log' },
  { path: path.join(TINYCLAW_LOGS_DIR, 'telegram.log'), source: 'telegram.log' },
  { path: path.join(TINYCLAW_LOGS_DIR, 'heartbeat.log'), source: 'heartbeat.log' },
];

const WORKSPACES = [
  { path: path.join(HOME, 'claudeclaw', 'elliot'), agent: 'elliot' },
  { path: path.join(HOME, 'claudeclaw', 'trader'), agent: 'trader' },
  { path: path.join(HOME, 'claudeclaw', 'dev'), agent: 'dev' },
];

const SKIP_DIRS = new Set(['node_modules', '__pycache__', '.git', '.next', '.cache', 'cache', '.tinyclaw']);
const SKIP_FILE_PATTERNS = ['.env', 'credentials', 'secrets', '.key', '.pem'];
const INDEXABLE_EXT = new Set(['.md', '.py', '.json', '.ts', '.tsx', '.js', '.sh', '.txt']);

// ============================================================================
// Parsers (inlined to avoid import complexity)
// ============================================================================

const LOCAL_TIME_RE = /^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+(.+)$/;
const ISO_LEVEL_RE = /^\[(\d{4}-\d{2}-\d{2}T[\d:.]+Z)\]\s+\[(\w+)\]\s+(.+)$/;
const AGENT_NAMES = ['elliot', 'trader', 'dev'];

// Sensitive value patterns for redaction
const KV_REDACT = [
  /("(?:[^"]*(?:key|secret|token|password|private|passphrase|credential)[^"]*)")\s*:\s*"([^"]+)"/gi,
  /\b([A-Z_]*(?:KEY|SECRET|TOKEN|PASSWORD|PRIVATE|PASSPHRASE|CREDENTIAL)[A-Z_]*)\s*=\s*["']?([^\s"']+)["']?/gi,
];

function redact(text: string): string {
  let result = text;
  for (const pattern of KV_REDACT) {
    pattern.lastIndex = 0;
    result = result.replace(pattern, (match, key, value) => {
      if (value.length <= 8) return match.replace(value, '****');
      return match.replace(value, value.slice(0, 4) + '***' + value.slice(-4));
    });
  }
  return result;
}

function isSensitiveFile(filePath: string): boolean {
  const lower = filePath.toLowerCase();
  return SKIP_FILE_PATTERNS.some((p) => lower.includes(p));
}

function detectAgent(message: string): string | null {
  const lower = message.toLowerCase();
  for (const name of AGENT_NAMES) {
    if (lower.includes(name)) return name;
  }
  return null;
}

interface LogEntry {
  timestamp: string;
  source: string;
  level: string | null;
  agent: string | null;
  eventType: string | null;
  message: string;
  raw: string;
}

function parseLogLine(line: string, source: string): LogEntry | null {
  const trimmed = line.trim();
  if (!trimmed) return null;

  // Skip queue.log debug spam
  if (source === 'queue.log' && trimmed.includes('[DEBUG]') && trimmed.includes('message(s) in queue')) {
    return null;
  }

  let match = ISO_LEVEL_RE.exec(trimmed);
  if (match) {
    return {
      timestamp: match[1],
      source,
      level: match[2],
      agent: detectAgent(match[3]),
      eventType: null,
      message: redact(match[3]),
      raw: redact(trimmed),
    };
  }

  match = LOCAL_TIME_RE.exec(trimmed);
  if (match) {
    return {
      timestamp: match[1].replace(' ', 'T') + 'Z',
      source,
      level: 'INFO',
      agent: detectAgent(match[2]),
      eventType: null,
      message: redact(match[2]),
      raw: redact(trimmed),
    };
  }

  return {
    timestamp: new Date().toISOString(),
    source,
    level: null,
    agent: null,
    eventType: null,
    message: redact(trimmed),
    raw: redact(trimmed),
  };
}

function parseEventFile(content: string): LogEntry | null {
  try {
    const event = JSON.parse(content.trim());
    const timestamp = new Date(event.timestamp).toISOString();
    const agent = event.agentId || null;
    const eventType = event.type || 'unknown';

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
        message = `Response (${event.responseLength} chars): ${preview}`;
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
      message: redact(message),
      raw: redact(content.trim()),
    };
  } catch {
    return null;
  }
}

// ============================================================================
// Database setup
// ============================================================================

fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });
const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');
db.pragma('synchronous = NORMAL');

// Schema
db.exec(`
  CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    level TEXT,
    agent TEXT,
    event_type TEXT,
    message TEXT NOT NULL,
    raw TEXT,
    created_at TEXT DEFAULT (datetime('now'))
  );
  CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity(timestamp DESC);
  CREATE INDEX IF NOT EXISTS idx_activity_agent ON activity(agent);
  CREATE INDEX IF NOT EXISTS idx_activity_source ON activity(source);

  CREATE TABLE IF NOT EXISTS trading_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    balance REAL,
    total_trades INTEGER,
    total_pnl REAL,
    daily_pnl REAL,
    trades_today INTEGER,
    open_positions_json TEXT,
    open_orders_json TEXT,
    last_scan TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source_file TEXT,
    market TEXT,
    city TEXT,
    side TEXT,
    amount REAL,
    price REAL,
    edge_pct REAL,
    confidence REAL,
    action TEXT,
    status TEXT,
    pnl REAL,
    order_id TEXT,
    url TEXT,
    raw TEXT,
    return_amount REAL,
    UNIQUE(timestamp, market, action)
  );
  CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp DESC);
  CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);

  CREATE TABLE IF NOT EXISTS ingest_state (
    file_path TEXT PRIMARY KEY,
    byte_offset INTEGER DEFAULT 0,
    last_modified TEXT,
    file_count INTEGER DEFAULT 0
  );

  CREATE TABLE IF NOT EXISTS exit_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    market TEXT NOT NULL,
    entry_price REAL,
    current_edge REAL,
    position_json TEXT,
    acknowledged INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS balance_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    balance REAL NOT NULL,
    event TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_balance_history_ts ON balance_history(timestamp);
`);

try {
  db.exec(`
    CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
      source, content, timestamp
    );
  `);
} catch {
  // Already exists
}

// Prepared statements
const insertActivity = db.prepare(`
  INSERT INTO activity (timestamp, source, level, agent, event_type, message, raw)
  VALUES (?, ?, ?, ?, ?, ?, ?)
`);

const upsertTradingState = db.prepare(`
  INSERT INTO trading_state (id, balance, total_trades, total_pnl, daily_pnl, trades_today, open_positions_json, open_orders_json, last_scan, updated_at)
  VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
  ON CONFLICT(id) DO UPDATE SET
    balance=excluded.balance, total_trades=excluded.total_trades,
    total_pnl=excluded.total_pnl, daily_pnl=excluded.daily_pnl,
    trades_today=excluded.trades_today, open_positions_json=excluded.open_positions_json,
    open_orders_json=excluded.open_orders_json,
    last_scan=excluded.last_scan, updated_at=datetime('now')
`);

const insertTrade = db.prepare(`
  INSERT OR IGNORE INTO trades (timestamp, source_file, market, city, side, amount, price, edge_pct, confidence, action, status, pnl, order_id, url, raw)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`);

const getIngestState = db.prepare('SELECT * FROM ingest_state WHERE file_path = ?');
const upsertIngestState = db.prepare(`
  INSERT INTO ingest_state (file_path, byte_offset, last_modified, file_count)
  VALUES (?, ?, ?, ?)
  ON CONFLICT(file_path) DO UPDATE SET
    byte_offset=excluded.byte_offset, last_modified=excluded.last_modified,
    file_count=excluded.file_count
`);

const insertSearch = db.prepare('INSERT INTO search_index (source, content, timestamp) VALUES (?, ?, ?)');

const insertExitAlert = db.prepare(`
  INSERT INTO exit_alerts (timestamp, market, entry_price, current_edge, position_json)
  VALUES (?, ?, ?, ?, ?)
`);

const getRecentAlerts = db.prepare(`
  SELECT market FROM exit_alerts WHERE market = ? AND created_at > datetime('now', '-1 hour')
`);

const insertBalanceHistory = db.prepare(`
  INSERT INTO balance_history (timestamp, balance, event) VALUES (?, ?, ?)
`);

const insertResolvedTrade = db.prepare(`
  INSERT OR IGNORE INTO trades (timestamp, source_file, market, side, amount, price, edge_pct, action, status, pnl, return_amount, raw)
  VALUES (?, 'trading_state.json', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`);

// ============================================================================
// Ingestion functions
// ============================================================================

function ingestLogFile(filePath: string, source: string): number {
  if (!fs.existsSync(filePath)) return 0;

  const stats = fs.statSync(filePath);
  const state = getIngestState.get(filePath) as any;
  let offset = state?.byte_offset || 0;

  // Log rotation detection: if file is smaller than offset, reset
  if (stats.size < offset) {
    console.log(`  [rotation] ${source}: file size ${stats.size} < offset ${offset}, resetting`);
    offset = 0;
  }

  if (stats.size === offset) return 0; // No new data

  const fd = fs.openSync(filePath, 'r');
  const buffer = Buffer.alloc(stats.size - offset);
  fs.readSync(fd, buffer, 0, buffer.length, offset);
  fs.closeSync(fd);

  const newData = buffer.toString('utf-8');
  const lines = newData.split('\n');
  let count = 0;

  const insertMany = db.transaction((entries: LogEntry[]) => {
    for (const entry of entries) {
      insertActivity.run(
        entry.timestamp, entry.source, entry.level,
        entry.agent, entry.eventType, entry.message, entry.raw
      );
    }
  });

  const entries: LogEntry[] = [];
  for (const line of lines) {
    const entry = parseLogLine(line, source);
    if (entry) {
      entries.push(entry);
      count++;
    }
  }

  if (entries.length > 0) {
    insertMany(entries);
  }

  upsertIngestState.run(filePath, stats.size, stats.mtime.toISOString(), 0);
  return count;
}

function ingestEvents(): number {
  if (!fs.existsSync(TINYCLAW_EVENTS_DIR)) return 0;

  const state = getIngestState.get(TINYCLAW_EVENTS_DIR) as any;
  const processedCount = state?.file_count || 0;

  const allFiles = fs.readdirSync(TINYCLAW_EVENTS_DIR)
    .filter((f) => f.endsWith('.json'))
    .sort();

  if (allFiles.length <= processedCount) return 0;

  const newFiles = allFiles.slice(processedCount);
  let count = 0;

  const insertMany = db.transaction((entries: LogEntry[]) => {
    for (const entry of entries) {
      insertActivity.run(
        entry.timestamp, entry.source, entry.level,
        entry.agent, entry.eventType, entry.message, entry.raw
      );
    }
  });

  const entries: LogEntry[] = [];
  for (const file of newFiles) {
    try {
      const content = fs.readFileSync(path.join(TINYCLAW_EVENTS_DIR, file), 'utf-8');
      const entry = parseEventFile(content);
      if (entry) {
        entries.push(entry);
        count++;
      }
    } catch {
      // Skip unreadable files
    }
  }

  if (entries.length > 0) {
    insertMany(entries);
  }

  upsertIngestState.run(TINYCLAW_EVENTS_DIR, 0, new Date().toISOString(), allFiles.length);
  return count;
}

// ============================================================================
// Position snapshot tracking
// ============================================================================

interface PositionSnapshot {
  market: string;
  side: string;
  entry_price: number;
  cost_basis: number;
  edge_pct: number;
  raw: any;
}

let previousPositions: PositionSnapshot[] = [];
let previousBalance: number | null = null;

function normalizePosition(pos: any): PositionSnapshot {
  return {
    market: pos.market || pos.market_name || 'unknown',
    side: pos.side || '',
    entry_price: pos.entry_price ?? 0,
    cost_basis: pos.cost_basis ?? pos.position_size ?? 0,
    edge_pct: pos.edge_pct ?? pos.entry_edge ?? 0,
    raw: pos,
  };
}

function detectResolvedPositions(oldPositions: PositionSnapshot[], newPositions: PositionSnapshot[], newBalance: number): void {
  const newMarkets = new Set(newPositions.map((p) => p.market));

  for (const old of oldPositions) {
    if (!newMarkets.has(old.market)) {
      // Position disappeared — it was resolved/exited
      const now = new Date().toISOString();
      const balanceDelta = previousBalance !== null ? newBalance - previousBalance : null;

      // Estimate PnL: if we know previous balance, the delta is likely from this exit
      // (imprecise if multiple positions resolve simultaneously, but good enough)
      const pnl = balanceDelta !== null && oldPositions.length - newPositions.length === 1
        ? Math.round(balanceDelta * 100) / 100
        : null;

      // return_amount = cost + pnl (what came back from the market)
      const returnAmount = pnl !== null ? Math.round((old.cost_basis + pnl) * 100) / 100 : null;

      insertResolvedTrade.run(
        now,
        old.market,
        old.side,
        old.cost_basis,
        old.entry_price,
        old.edge_pct,
        `${old.side} (resolved)`,
        'RESOLVED',
        pnl,
        returnAmount,
        JSON.stringify(old.raw)
      );

      console.log(`  [TRADE RESOLVED] ${old.market} | ${old.side} | entry: ${old.entry_price} | cost: $${old.cost_basis}${pnl !== null ? ` | pnl: $${pnl}` : ''}`);
    }
  }
}

// Track missing file warnings (only warn once per file)
const missingFileWarned = new Set<string>();

function warnMissingFile(filePath: string, label: string): void {
  if (!missingFileWarned.has(filePath)) {
    console.warn(`  [MISSING] ${label}: ${filePath} — trader agent needs to create this file`);
    missingFileWarned.add(filePath);
  }
}

function readOpenOrders(): any[] {
  if (!fs.existsSync(OPEN_ORDERS_FILE)) {
    warnMissingFile(OPEN_ORDERS_FILE, 'open_orders.json');
    return [];
  }
  try {
    const content = fs.readFileSync(OPEN_ORDERS_FILE, 'utf-8');
    return JSON.parse(content) || [];
  } catch {
    return [];
  }
}

function ingestTradingState(): boolean {
  if (!fs.existsSync(TRADING_STATE_FILE)) {
    warnMissingFile(TRADING_STATE_FILE, 'trading_state.json');
    return false;
  }

  const state = getIngestState.get(TRADING_STATE_FILE) as any;
  const stats = fs.statSync(TRADING_STATE_FILE);
  const openOrdersChanged = hasOpenOrdersChanged();

  if (state?.last_modified === stats.mtime.toISOString() && !openOrdersChanged) return false;

  try {
    const content = fs.readFileSync(TRADING_STATE_FILE, 'utf-8');
    const data = JSON.parse(content);

    // Read open_orders from trading_state.json or from separate open_orders.json
    const openOrders = data.open_orders ?? readOpenOrders();

    // Handle both formats: balance can be a number or { usdc: N }
    const balance = data.balance_usdc ?? (typeof data.balance === 'object'
      ? (data.balance?.usdc ?? data.balance?.available ?? 0)
      : (data.balance ?? data.simulated_balance ?? 0));

    // Handle both field names: active_positions (new) or open_positions (old)
    const positions = data.active_positions || data.open_positions || data.positions || [];

    const totalTrades = data.total_trades ?? data.stats?.total_active_positions ?? 0;
    const totalPnl = data.total_pnl ?? 0;
    const dailyPnl = data.daily_pnl ?? 0;
    const tradesToday = data.trades_today ?? 0;
    const lastScan = data.last_scan ?? data.last_updated ?? null;

    // Normalize current positions for diffing
    const currentPositions = positions.map(normalizePosition);

    // Detect resolved positions (present before, gone now)
    if (previousPositions.length > 0) {
      detectResolvedPositions(previousPositions, currentPositions, balance);
    }

    // Record balance change
    const now = new Date().toISOString();
    if (previousBalance !== null && balance !== previousBalance) {
      const delta = balance - previousBalance;
      insertBalanceHistory.run(now, balance, `balance_change: ${delta >= 0 ? '+' : ''}${delta.toFixed(2)}`);
      console.log(`  [BALANCE] $${previousBalance.toFixed(2)} → $${balance.toFixed(2)} (${delta >= 0 ? '+' : ''}${delta.toFixed(2)})`);
    } else if (previousBalance === null) {
      // First observation — seed balance history
      insertBalanceHistory.run(now, balance, 'initial');
    }

    // Update snapshots for next cycle
    previousPositions = currentPositions;
    previousBalance = balance;

    upsertTradingState.run(
      balance,
      totalTrades,
      totalPnl,
      dailyPnl,
      tradesToday,
      JSON.stringify(positions),
      JSON.stringify(openOrders),
      lastScan
    );

    // Check for 2x exit triggers
    for (const pos of positions) {
      const market = pos.market || pos.market_name || 'unknown';
      const edgePct = pos.edge_pct ?? pos.entry_edge ?? 0;
      if (pos.entry_price && pos.entry_price > 0 && pos.current_price >= 2 * pos.entry_price) {
        // Only alert once per market per hour
        const existing = getRecentAlerts.get(market);
        if (!existing) {
          insertExitAlert.run(
            new Date().toISOString(),
            market,
            pos.entry_price,
            edgePct,
            JSON.stringify(pos)
          );
          console.log(`  [EXIT TRIGGER] ${market} @ ${pos.current_price} (2x entry ${pos.entry_price})`);
        }
      }
    }

    upsertIngestState.run(TRADING_STATE_FILE, 0, stats.mtime.toISOString(), 0);
    if (openOrdersChanged) {
      const orderStats = fs.statSync(OPEN_ORDERS_FILE);
      upsertIngestState.run(OPEN_ORDERS_FILE, 0, orderStats.mtime.toISOString(), 0);
    }
    return true;
  } catch (e) {
    console.error(`  Error parsing trading state: ${e}`);
    return false;
  }
}

function hasOpenOrdersChanged(): boolean {
  if (!fs.existsSync(OPEN_ORDERS_FILE)) return false;
  try {
    const stats = fs.statSync(OPEN_ORDERS_FILE);
    const state = getIngestState.get(OPEN_ORDERS_FILE) as any;
    return state?.last_modified !== stats.mtime.toISOString();
  } catch {
    return false;
  }
}

function ingestJournals(): number {
  if (!fs.existsSync(JOURNAL_DIR)) return 0;

  let totalCount = 0;
  const files = fs.readdirSync(JOURNAL_DIR);

  for (const file of files) {
    const filePath = path.join(JOURNAL_DIR, file);
    const stats = fs.statSync(filePath);
    const state = getIngestState.get(filePath) as any;

    if (file.endsWith('.jsonl')) {
      // JSONL: tail from offset
      let offset = state?.byte_offset || 0;

      // Rotation check
      if (stats.size < offset) {
        offset = 0;
      }

      if (stats.size === offset) continue;

      const fd = fs.openSync(filePath, 'r');
      const buffer = Buffer.alloc(stats.size - offset);
      fs.readSync(fd, buffer, 0, buffer.length, offset);
      fs.closeSync(fd);

      const lines = buffer.toString('utf-8').split('\n');
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const data = JSON.parse(line.trim());
          if (!data.timestamp) continue;

          let status = 'UNKNOWN';
          if (file.includes('hypothetical')) status = 'HYPOTHETICAL';
          else if (file.includes('paper')) status = data.status || 'PAPER';

          insertTrade.run(
            data.timestamp, file,
            data.market || data.question || null,
            data.city || null,
            data.side || null,
            data.position_size || data.amount || data.hypothetical_size || null,
            data.entry_price || data.market_yes_price || data.price || null,
            data.edge_pct || data.adjusted_edge_pct || null,
            data.forecast_confidence || data.confidence || null,
            data.action || null,
            status,
            data.pnl || null,
            data.order_id || null,
            data.url || null,
            redact(line.trim())
          );
          totalCount++;
        } catch {
          // Skip unparseable lines
        }
      }

      upsertIngestState.run(filePath, stats.size, stats.mtime.toISOString(), 0);
    } else if (file.endsWith('.md')) {
      // Markdown: re-parse if mtime changed
      if (state?.last_modified === stats.mtime.toISOString()) continue;

      const content = fs.readFileSync(filePath, 'utf-8');

      // Index for search
      try {
        insertSearch.run(filePath, redact(content), stats.mtime.toISOString());
      } catch {
        // May already exist
      }

      // Parse trade entries
      const sections = content.split(/^### Trade @/m);
      for (const section of sections.slice(1)) {
        const timestampMatch = section.match(/(\d{4}-\d{2}-\d{2}T[\d:]+)/);
        if (!timestampMatch) continue;

        const fields: Record<string, string> = {};
        for (const l of section.split('\n')) {
          const m = l.match(/^\s*-\s+\*\*(\w+):\*\*\s+(.+)$/);
          if (m) fields[m[1].toLowerCase()] = m[2].trim();
        }

        insertTrade.run(
          timestampMatch[1], file,
          fields.market || null, null,
          fields.side || null,
          fields.amount ? parseFloat(fields.amount.replace('$', '')) : null,
          fields.price ? parseFloat(fields.price.replace('%', '')) / 100 : null,
          null, null,
          fields.side ? `BUY ${fields.side}` : null,
          fields.outcome === '*pending*' ? 'PENDING' : (fields.outcome || 'UNKNOWN'),
          null, null, null,
          redact(`### Trade @${section.slice(0, 500)}`)
        );
        totalCount++;
      }

      upsertIngestState.run(filePath, 0, stats.mtime.toISOString(), 0);
    }
  }

  return totalCount;
}

function indexWorkspaces(): number {
  let count = 0;

  function walkDir(dirPath: string) {
    if (!fs.existsSync(dirPath)) return;

    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dirPath, { withFileTypes: true });
    } catch {
      return;
    }

    for (const entry of entries) {
      const fullPath = path.join(dirPath, entry.name);

      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name)) {
          walkDir(fullPath);
        }
        continue;
      }

      if (!entry.isFile()) continue;

      const ext = path.extname(entry.name).toLowerCase();
      if (!INDEXABLE_EXT.has(ext)) continue;
      if (isSensitiveFile(entry.name)) continue;

      try {
        const stats = fs.statSync(fullPath);
        const state = getIngestState.get(fullPath) as any;

        if (state?.last_modified === stats.mtime.toISOString()) continue;

        // Only index files under 500KB
        if (stats.size > 500 * 1024) continue;

        const content = fs.readFileSync(fullPath, 'utf-8');
        const redacted = redact(content);

        // Delete old entry if exists, then insert
        try {
          db.prepare('DELETE FROM search_index WHERE source = ?').run(fullPath);
        } catch { /* ignore */ }

        insertSearch.run(fullPath, redacted, stats.mtime.toISOString());
        upsertIngestState.run(fullPath, 0, stats.mtime.toISOString(), 0);
        count++;
      } catch {
        // Skip unreadable files
      }
    }
  }

  for (const ws of WORKSPACES) {
    walkDir(ws.path);
  }

  return count;
}

// ============================================================================
// Main loop
// ============================================================================

const POLL_INTERVAL_MS = 2000;
const SEARCH_INDEX_INTERVAL_MS = 300000; // Re-index workspaces every 5 minutes
let lastSearchIndex = 0;
let cycleCount = 0;

function runCycle() {
  const now = Date.now();
  cycleCount++;

  let totalIngested = 0;

  // 1. Tail log files
  for (const logFile of LOG_FILES) {
    const count = ingestLogFile(logFile.path, logFile.source);
    if (count > 0) {
      console.log(`  [log] ${logFile.source}: +${count} entries`);
      totalIngested += count;
    }
  }

  // 2. Ingest events
  const eventCount = ingestEvents();
  if (eventCount > 0) {
    console.log(`  [events] +${eventCount} entries`);
    totalIngested += eventCount;
  }

  // 3. Update trading state
  const tradingUpdated = ingestTradingState();
  if (tradingUpdated) {
    console.log('  [trading] state updated');
  }

  // 4. Ingest journals
  const journalCount = ingestJournals();
  if (journalCount > 0) {
    console.log(`  [journals] +${journalCount} trades`);
    totalIngested += journalCount;
  }

  // 5. Re-index workspaces periodically
  if (now - lastSearchIndex > SEARCH_INDEX_INTERVAL_MS) {
    const searchCount = indexWorkspaces();
    if (searchCount > 0 || lastSearchIndex === 0) {
      console.log(`  [search] indexed ${searchCount} files`);
    }
    lastSearchIndex = now;
  }

  // Periodic status (every 30 cycles = ~60 seconds)
  if (cycleCount % 30 === 0) {
    const activityCount = (db.prepare('SELECT COUNT(*) as c FROM activity').get() as any).c;
    const tradeCount = (db.prepare('SELECT COUNT(*) as c FROM trades').get() as any).c;
    const searchCount = (db.prepare('SELECT COUNT(*) as c FROM search_index').get() as any).c;
    console.log(`[status] activity: ${activityCount}, trades: ${tradeCount}, search: ${searchCount}`);
  }
}

// ============================================================================
// Entry point
// ============================================================================

console.log('Mission Control Watcher starting...');
console.log(`  Database: ${DB_PATH}`);
console.log(`  Logs: ${TINYCLAW_LOGS_DIR}`);
console.log(`  Events: ${TINYCLAW_EVENTS_DIR}`);
console.log(`  Trading: ${TRADING_STATE_FILE}`);
console.log(`  Open Orders: ${OPEN_ORDERS_FILE}`);
console.log(`  Journals: ${JOURNAL_DIR}`);
console.log(`  Poll interval: ${POLL_INTERVAL_MS}ms`);
console.log('');

// Check for missing trader files on startup
if (!fs.existsSync(TRADING_STATE_FILE)) {
  warnMissingFile(TRADING_STATE_FILE, 'trading_state.json');
}
if (!fs.existsSync(OPEN_ORDERS_FILE)) {
  warnMissingFile(OPEN_ORDERS_FILE, 'open_orders.json');
}

// Initial full run
console.log('Running initial ingestion...');
runCycle();
console.log('Initial ingestion complete.\n');

// Start polling
console.log('Watching for changes...');
const interval = setInterval(runCycle, POLL_INTERVAL_MS);

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\nShutting down watcher...');
  clearInterval(interval);
  db.close();
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.log('\nShutting down watcher...');
  clearInterval(interval);
  db.close();
  process.exit(0);
});
