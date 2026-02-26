#!/usr/bin/env tsx
"use strict";
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));

// scripts/watcher.ts
var import_better_sqlite3 = __toESM(require("better-sqlite3"));
var import_fs = __toESM(require("fs"));
var import_path = __toESM(require("path"));
var import_os = __toESM(require("os"));
var HOME = import_os.default.homedir();
var DB_PATH = import_path.default.join(HOME, "claudeclaw", "mission-control", "data.db");
var TINYCLAW_LOGS_DIR = import_path.default.join(HOME, ".tinyclaw", "logs");
var TINYCLAW_EVENTS_DIR = import_path.default.join(HOME, ".tinyclaw", "events");
var TRADER_BASE = import_path.default.join(HOME, "claudeclaw", "trader", "polymarket-trader");
var TRADING_STATE_FILE = import_path.default.join(TRADER_BASE, "trading_state.json");
var OPEN_ORDERS_FILE = import_path.default.join(TRADER_BASE, "open_orders.json");
var SCAN_DETAILS_FILE = import_path.default.join(TRADER_BASE, "scan_details.jsonl");
var JOURNAL_DIR = import_path.default.join(TRADER_BASE, "journal");
var LOG_FILES = [
  { path: import_path.default.join(TINYCLAW_LOGS_DIR, "daemon.log"), source: "daemon.log" },
  { path: import_path.default.join(TINYCLAW_LOGS_DIR, "queue.log"), source: "queue.log" },
  { path: import_path.default.join(TINYCLAW_LOGS_DIR, "telegram.log"), source: "telegram.log" },
  { path: import_path.default.join(TINYCLAW_LOGS_DIR, "heartbeat.log"), source: "heartbeat.log" },
  { path: import_path.default.join(TINYCLAW_LOGS_DIR, "trader.log"), source: "trader.log" }
];
var WORKSPACES = [
  { path: import_path.default.join(HOME, "claudeclaw", "elliot"), agent: "elliot" },
  { path: import_path.default.join(HOME, "claudeclaw", "trader"), agent: "trader" },
  { path: import_path.default.join(HOME, "claudeclaw", "dev"), agent: "dev" }
];
var SKIP_DIRS = /* @__PURE__ */ new Set(["node_modules", "__pycache__", ".git", ".next", ".cache", "cache", ".tinyclaw"]);
var SKIP_FILE_PATTERNS = [".env", "credentials", "secrets", ".key", ".pem"];
var INDEXABLE_EXT = /* @__PURE__ */ new Set([".md", ".py", ".json", ".ts", ".tsx", ".js", ".sh", ".txt"]);
var LOCAL_TIME_RE = /^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+(.+)$/;
var ISO_LEVEL_RE = /^\[(\d{4}-\d{2}-\d{2}T[\d:.]+Z)\]\s+\[(\w+)\]\s+(.+)$/;
var AGENT_NAMES = ["elliot", "trader", "dev"];
var KV_REDACT = [
  /("(?:[^"]*(?:key|secret|token|password|private|passphrase|credential)[^"]*)")\s*:\s*"([^"]+)"/gi,
  /\b([A-Z_]*(?:KEY|SECRET|TOKEN|PASSWORD|PRIVATE|PASSPHRASE|CREDENTIAL)[A-Z_]*)\s*=\s*["']?([^\s"']+)["']?/gi
];
function redact(text) {
  let result = text;
  for (const pattern of KV_REDACT) {
    pattern.lastIndex = 0;
    result = result.replace(pattern, (match, key, value) => {
      if (value.length <= 8) return match.replace(value, "****");
      return match.replace(value, value.slice(0, 4) + "***" + value.slice(-4));
    });
  }
  return result;
}
function isSensitiveFile(filePath) {
  const lower = filePath.toLowerCase();
  return SKIP_FILE_PATTERNS.some((p) => lower.includes(p));
}
function detectAgent(message) {
  const lower = message.toLowerCase();
  for (const name of AGENT_NAMES) {
    if (lower.includes(name)) return name;
  }
  return null;
}
function parseLogLine(line, source) {
  const trimmed = line.trim();
  if (!trimmed) return null;
  if (source === "queue.log" && trimmed.includes("[DEBUG]") && trimmed.includes("message(s) in queue")) {
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
      raw: redact(trimmed)
    };
  }
  match = LOCAL_TIME_RE.exec(trimmed);
  if (match) {
    return {
      timestamp: match[1].replace(" ", "T") + "Z",
      source,
      level: "INFO",
      agent: detectAgent(match[2]),
      eventType: null,
      message: redact(match[2]),
      raw: redact(trimmed)
    };
  }
  return {
    timestamp: (/* @__PURE__ */ new Date()).toISOString(),
    source,
    level: null,
    agent: null,
    eventType: null,
    message: redact(trimmed),
    raw: redact(trimmed)
  };
}
function parseEventFile(content) {
  try {
    const event = JSON.parse(content.trim());
    const timestamp = new Date(event.timestamp).toISOString();
    const agent = event.agentId || null;
    const eventType = event.type || "unknown";
    let message;
    switch (eventType) {
      case "processor_start":
        message = `Queue processor started with agents: ${(event.agents || []).join(", ")}`;
        break;
      case "message_received":
        message = `[${event.channel}] ${event.sender}: ${(event.message || "").slice(0, 200)}`;
        break;
      case "agent_routed":
        message = `Routed to ${event.agentName} (${event.provider}/${event.model})`;
        break;
      case "chain_step_start":
        message = `Chain step started: ${event.stepType || "unknown"}`;
        break;
      case "chain_step_done":
        message = `Chain step completed: ${event.stepType || "unknown"}`;
        break;
      case "response_ready": {
        const preview = (event.responseText || "").slice(0, 200);
        message = `Response (${event.responseLength} chars): ${preview}`;
        break;
      }
      default:
        message = `Event: ${eventType}`;
    }
    return {
      timestamp,
      source: "event",
      level: null,
      agent,
      eventType,
      message: redact(message),
      raw: redact(content.trim())
    };
  } catch {
    return null;
  }
}
import_fs.default.mkdirSync(import_path.default.dirname(DB_PATH), { recursive: true });
var db = new import_better_sqlite3.default(DB_PATH);
db.pragma("journal_mode = WAL");
db.pragma("synchronous = NORMAL");
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

  CREATE TABLE IF NOT EXISTS scan_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,
    scan_timestamp TEXT NOT NULL,
    city TEXT,
    market TEXT,
    side TEXT,
    edge REAL,
    price REAL,
    confidence REAL,
    sources TEXT,
    forecast_temp TEXT,
    liquidity REAL,
    rejection_reason TEXT,
    qualified INTEGER DEFAULT 0
  );
  CREATE INDEX IF NOT EXISTS idx_scan_details_scan ON scan_details(scan_id);
  CREATE INDEX IF NOT EXISTS idx_scan_details_ts ON scan_details(scan_timestamp DESC);

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
}
var insertActivity = db.prepare(`
  INSERT INTO activity (timestamp, source, level, agent, event_type, message, raw)
  VALUES (?, ?, ?, ?, ?, ?, ?)
`);
var upsertTradingState = db.prepare(`
  INSERT INTO trading_state (id, balance, total_trades, total_pnl, daily_pnl, trades_today, open_positions_json, open_orders_json, last_scan, updated_at)
  VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
  ON CONFLICT(id) DO UPDATE SET
    balance=excluded.balance, total_trades=excluded.total_trades,
    total_pnl=excluded.total_pnl, daily_pnl=excluded.daily_pnl,
    trades_today=excluded.trades_today, open_positions_json=excluded.open_positions_json,
    open_orders_json=excluded.open_orders_json,
    last_scan=excluded.last_scan, updated_at=datetime('now')
`);
var insertTrade = db.prepare(`
  INSERT OR IGNORE INTO trades (timestamp, source_file, market, city, side, amount, price, edge_pct, confidence, action, status, pnl, order_id, url, raw, return_amount)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`);
var getIngestState = db.prepare("SELECT * FROM ingest_state WHERE file_path = ?");
var upsertIngestState = db.prepare(`
  INSERT INTO ingest_state (file_path, byte_offset, last_modified, file_count)
  VALUES (?, ?, ?, ?)
  ON CONFLICT(file_path) DO UPDATE SET
    byte_offset=excluded.byte_offset, last_modified=excluded.last_modified,
    file_count=excluded.file_count
`);
var insertSearch = db.prepare("INSERT INTO search_index (source, content, timestamp) VALUES (?, ?, ?)");
var insertExitAlert = db.prepare(`
  INSERT INTO exit_alerts (timestamp, market, entry_price, current_edge, position_json)
  VALUES (?, ?, ?, ?, ?)
`);
var getRecentAlerts = db.prepare(`
  SELECT market FROM exit_alerts WHERE market = ? AND created_at > datetime('now', '-1 hour')
`);
var insertBalanceHistory = db.prepare(`
  INSERT INTO balance_history (timestamp, balance, event) VALUES (?, ?, ?)
`);
var insertResolvedTrade = db.prepare(`
  INSERT OR IGNORE INTO trades (timestamp, source_file, market, side, amount, price, edge_pct, action, status, pnl, return_amount, raw)
  VALUES (?, 'trading_state.json', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`);
var insertScanDetail = db.prepare(`
  INSERT INTO scan_details (scan_id, scan_timestamp, city, market, side, edge, price, confidence, sources, forecast_temp, liquidity, rejection_reason, qualified)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`);
function ingestLogFile(filePath, source) {
  if (!import_fs.default.existsSync(filePath)) return 0;
  const stats = import_fs.default.statSync(filePath);
  const state = getIngestState.get(filePath);
  let offset = state?.byte_offset || 0;
  if (stats.size < offset) {
    console.log(`  [rotation] ${source}: file size ${stats.size} < offset ${offset}, resetting`);
    offset = 0;
  }
  if (stats.size === offset) return 0;
  const fd = import_fs.default.openSync(filePath, "r");
  const buffer = Buffer.alloc(stats.size - offset);
  import_fs.default.readSync(fd, buffer, 0, buffer.length, offset);
  import_fs.default.closeSync(fd);
  const newData = buffer.toString("utf-8");
  const lines = newData.split("\n");
  let count = 0;
  const insertMany = db.transaction((entries2) => {
    for (const entry of entries2) {
      insertActivity.run(
        entry.timestamp,
        entry.source,
        entry.level,
        entry.agent,
        entry.eventType,
        entry.message,
        entry.raw
      );
    }
  });
  const entries = [];
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
function ingestEvents() {
  if (!import_fs.default.existsSync(TINYCLAW_EVENTS_DIR)) return 0;
  const state = getIngestState.get(TINYCLAW_EVENTS_DIR);
  const processedCount = state?.file_count || 0;
  const allFiles = import_fs.default.readdirSync(TINYCLAW_EVENTS_DIR).filter((f) => f.endsWith(".json")).sort();
  if (allFiles.length <= processedCount) return 0;
  const newFiles = allFiles.slice(processedCount);
  let count = 0;
  const insertMany = db.transaction((entries2) => {
    for (const entry of entries2) {
      insertActivity.run(
        entry.timestamp,
        entry.source,
        entry.level,
        entry.agent,
        entry.eventType,
        entry.message,
        entry.raw
      );
    }
  });
  const entries = [];
  for (const file of newFiles) {
    try {
      const content = import_fs.default.readFileSync(import_path.default.join(TINYCLAW_EVENTS_DIR, file), "utf-8");
      const entry = parseEventFile(content);
      if (entry) {
        entries.push(entry);
        count++;
      }
    } catch {
    }
  }
  if (entries.length > 0) {
    insertMany(entries);
  }
  upsertIngestState.run(TINYCLAW_EVENTS_DIR, 0, (/* @__PURE__ */ new Date()).toISOString(), allFiles.length);
  return count;
}
var previousPositions = [];
var previousBalance = null;
function normalizePosition(pos) {
  return {
    market: pos.market || pos.market_name || "unknown",
    side: pos.side || "",
    entry_price: pos.entry_price ?? 0,
    cost_basis: pos.cost_basis ?? pos.position_size ?? 0,
    edge_pct: pos.edge_pct ?? pos.entry_edge ?? 0,
    raw: pos
  };
}
function detectResolvedPositions(oldPositions, newPositions, newBalance) {
  const newMarkets = new Set(newPositions.map((p) => p.market));
  for (const old of oldPositions) {
    if (!newMarkets.has(old.market)) {
      const now = (/* @__PURE__ */ new Date()).toISOString();
      const balanceDelta = previousBalance !== null ? newBalance - previousBalance : null;
      const pnl = balanceDelta !== null && oldPositions.length - newPositions.length === 1 ? Math.round(balanceDelta * 100) / 100 : null;
      const returnAmount = pnl !== null ? Math.round((old.cost_basis + pnl) * 100) / 100 : null;
      insertResolvedTrade.run(
        now,
        old.market,
        old.side,
        old.cost_basis,
        old.entry_price,
        old.edge_pct,
        `${old.side} (resolved)`,
        "RESOLVED",
        pnl,
        returnAmount,
        JSON.stringify(old.raw)
      );
      console.log(`  [TRADE RESOLVED] ${old.market} | ${old.side} | entry: ${old.entry_price} | cost: $${old.cost_basis}${pnl !== null ? ` | pnl: $${pnl}` : ""}`);
    }
  }
}
var missingFileWarned = /* @__PURE__ */ new Set();
function warnMissingFile(filePath, label) {
  if (!missingFileWarned.has(filePath)) {
    console.warn(`  [MISSING] ${label}: ${filePath} \u2014 trader agent needs to create this file`);
    missingFileWarned.add(filePath);
  }
}
function readOpenOrders() {
  if (!import_fs.default.existsSync(OPEN_ORDERS_FILE)) {
    warnMissingFile(OPEN_ORDERS_FILE, "open_orders.json");
    return [];
  }
  try {
    const content = import_fs.default.readFileSync(OPEN_ORDERS_FILE, "utf-8");
    return JSON.parse(content) || [];
  } catch {
    return [];
  }
}
function ingestFilledOrders() {
  const orders = readOpenOrders();
  let count = 0;
  for (const order of orders) {
    if (order.status !== "FILLED") continue;
    const timestamp = order.time_placed || (/* @__PURE__ */ new Date()).toISOString();
    const market = order.question || order.market || "unknown";
    const city = order.city || null;
    const side = order.side || null;
    const amount = order.amount ?? null;
    const price = order.price ?? null;
    const edge = order.edge ?? null;
    const conf = order.conf ?? null;
    const action = side ? `BUY ${side}` : null;
    const orderId = order.order_id || null;
    try {
      const result = insertTrade.run(
        timestamp,
        "open_orders.json",
        market,
        city,
        side,
        amount,
        price,
        edge,
        conf,
        action,
        "EXECUTED",
        null,
        orderId,
        null,
        JSON.stringify(order).slice(0, 500),
        null
      );
      if (result.changes > 0) count++;
    } catch {
    }
  }
  if (count > 0) console.log(`  [ORDERS] Ingested ${count} filled orders as trades`);
}
function ingestTradingState() {
  if (!import_fs.default.existsSync(TRADING_STATE_FILE)) {
    warnMissingFile(TRADING_STATE_FILE, "trading_state.json");
    return false;
  }
  const state = getIngestState.get(TRADING_STATE_FILE);
  const stats = import_fs.default.statSync(TRADING_STATE_FILE);
  const openOrdersChanged = hasOpenOrdersChanged();
  if (state?.last_modified === stats.mtime.toISOString() && !openOrdersChanged) return false;
  try {
    const content = import_fs.default.readFileSync(TRADING_STATE_FILE, "utf-8");
    const data = JSON.parse(content);
    const openOrders = data.open_orders ?? readOpenOrders();
    const balance = data.balance_usdc ?? (typeof data.balance === "object" ? data.balance?.usdc ?? data.balance?.available ?? 0 : data.balance ?? data.simulated_balance ?? 0);
    const positions = [data.active_positions, data.open_positions, data.positions].find((arr) => Array.isArray(arr) && arr.length > 0) ?? [];
    const totalTrades = data.total_trades ?? data.stats?.total_active_positions ?? 0;
    const totalPnl = data.total_pnl ?? 0;
    const dailyPnl = data.daily_pnl ?? 0;
    const tradesToday = data.trades_today ?? 0;
    const lastScan = data.last_scan ?? data.last_updated ?? null;
    const currentPositions = positions.map(normalizePosition);
    if (previousPositions.length > 0) {
      detectResolvedPositions(previousPositions, currentPositions, balance);
    }
    const now = (/* @__PURE__ */ new Date()).toISOString();
    if (previousBalance !== null && balance !== previousBalance) {
      const delta = balance - previousBalance;
      insertBalanceHistory.run(now, balance, `balance_change: ${delta >= 0 ? "+" : ""}${delta.toFixed(2)}`);
      console.log(`  [BALANCE] $${previousBalance.toFixed(2)} \u2192 $${balance.toFixed(2)} (${delta >= 0 ? "+" : ""}${delta.toFixed(2)})`);
    } else if (previousBalance === null) {
      insertBalanceHistory.run(now, balance, "initial");
    }
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
    for (const pos of positions) {
      const market = pos.market || pos.market_name || "unknown";
      const edgePct = pos.edge_pct ?? pos.entry_edge ?? 0;
      if (pos.entry_price && pos.entry_price > 0 && pos.current_price >= 2 * pos.entry_price) {
        const existing = getRecentAlerts.get(market);
        if (!existing) {
          insertExitAlert.run(
            (/* @__PURE__ */ new Date()).toISOString(),
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
      const orderStats = import_fs.default.statSync(OPEN_ORDERS_FILE);
      upsertIngestState.run(OPEN_ORDERS_FILE, 0, orderStats.mtime.toISOString(), 0);
    }
    return true;
  } catch (e) {
    console.error(`  Error parsing trading state: ${e}`);
    return false;
  }
}
function hasOpenOrdersChanged() {
  if (!import_fs.default.existsSync(OPEN_ORDERS_FILE)) return false;
  try {
    const stats = import_fs.default.statSync(OPEN_ORDERS_FILE);
    const state = getIngestState.get(OPEN_ORDERS_FILE);
    return state?.last_modified !== stats.mtime.toISOString();
  } catch {
    return false;
  }
}
function ingestJournals() {
  if (!import_fs.default.existsSync(JOURNAL_DIR)) return 0;
  let totalCount = 0;
  const files = import_fs.default.readdirSync(JOURNAL_DIR);
  for (const file of files) {
    const filePath = import_path.default.join(JOURNAL_DIR, file);
    const stats = import_fs.default.statSync(filePath);
    const state = getIngestState.get(filePath);
    if (file.endsWith(".jsonl")) {
      let offset = state?.byte_offset || 0;
      if (stats.size < offset) {
        offset = 0;
      }
      if (stats.size === offset) continue;
      const fd = import_fs.default.openSync(filePath, "r");
      const buffer = Buffer.alloc(stats.size - offset);
      import_fs.default.readSync(fd, buffer, 0, buffer.length, offset);
      import_fs.default.closeSync(fd);
      const lines = buffer.toString("utf-8").split("\n");
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const data = JSON.parse(line.trim());
          if (!data.timestamp) continue;
          let status = "UNKNOWN";
          if (file.includes("hypothetical")) status = "HYPOTHETICAL";
          else if (file.includes("paper")) status = data.status || "PAPER";
          insertTrade.run(
            data.timestamp,
            file,
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
            redact(line.trim()),
            data.return_amount ?? null
          );
          totalCount++;
        } catch {
        }
      }
      upsertIngestState.run(filePath, stats.size, stats.mtime.toISOString(), 0);
    } else if (file.endsWith(".md")) {
      if (state?.last_modified === stats.mtime.toISOString()) continue;
      const content = import_fs.default.readFileSync(filePath, "utf-8");
      try {
        insertSearch.run(filePath, redact(content), stats.mtime.toISOString());
      } catch {
      }
      const dateMatch = file.match(/(\d{4}-\d{2}-\d{2})/);
      const fileDate = dateMatch ? dateMatch[1] : "";
      const sections = content.split(/^## (?:Trade[^-]*[-\u2014] |Position Exit [-\u2014] |Exit [-\u2014] |Confirmation Top-Up [-\u2014] )/m);
      const headerMatches = [...content.matchAll(/^## (Trade[^-]*[-\u2014] |Position Exit [-\u2014] |Exit [-\u2014] |Confirmation Top-Up [-\u2014] )(\d{2}:\d{2}:\d{2})/gm)];
      for (let i = 0; i < headerMatches.length; i++) {
        let section = sections[i + 1];
        if (!section) continue;
        const nextHeading = section.match(/^## /m);
        if (nextHeading?.index) section = section.slice(0, nextHeading.index);
        const headerType = headerMatches[i][1].trim();
        const time = headerMatches[i][2];
        const timestamp = fileDate ? `${fileDate}T${time}` : (/* @__PURE__ */ new Date()).toISOString();
        const isExit = headerType.startsWith("Position Exit") || headerType.startsWith("Exit");
        const fields = {};
        for (const l of section.split("\n")) {
          const m = l.match(/^\*\*([^*]+)\*\*:\s*(.+)$/);
          if (m) fields[m[1].toLowerCase().trim()] = m[2].trim();
          const m2 = l.match(/^\s*-\s+\*\*([^*]+)\*\*:\s*(.+)$/);
          if (m2) fields[m2[1].toLowerCase().trim()] = m2[2].trim();
          const m3 = l.match(/^([A-Z][A-Za-z &/]+):\s*(.+)$/);
          if (m3 && !fields[m3[1].toLowerCase().trim()]) {
            fields[m3[1].toLowerCase().trim()] = m3[2].trim();
          }
        }
        let status = "UNKNOWN";
        const rawStatus = fields.status || "";
        if (rawStatus.includes("EXECUTED") || rawStatus.includes("FILLED")) status = "EXECUTED";
        else if (rawStatus.includes("CLOSED")) status = "CLOSED";
        else if (rawStatus.includes("FAILED")) status = "FAILED";
        else if (isExit) status = "CLOSED";
        if (status === "FAILED") continue;
        const action = fields.action || (fields.side ? `BUY ${fields.side.replace(/^BUY\s+/i, "")}` : null);
        const side = fields.side?.replace(/^BUY\s+/i, "") || (action?.replace(/^BUY\s+/i, "") || null);
        const market = fields.market || fields.question || null;
        let costStr = fields.cost || fields.amount || fields.size || fields["cost basis"] || fields["expected cost"] || null;
        if (!costStr && fields.entry) {
          const costMatch = fields.entry.match(/\$([\d.]+)\s*cost(?:\s*basis)?/);
          if (costMatch) costStr = costMatch[1];
        }
        const amount = costStr ? parseFloat(String(costStr).replace(/[~$]/g, "")) : null;
        const priceStr = fields.price || fields["execution price"] || fields["entry price"] || fields["scan price"] || fields.entry?.match(/([\d.]+)¢/)?.[1] || null;
        const price = priceStr ? parseFloat(String(priceStr).replace(/[¢c]/g, "").replace(/\s*\(.*/, "")) / 100 : null;
        const edgeStr = fields.edge || fields["original edge"] || null;
        const edge = edgeStr ? parseFloat(String(edgeStr).replace(/%.*/, "")) : null;
        const pnlStr = fields["estimated p&l"] || fields.pnl || fields["p&l"] || null;
        let pnl = null;
        if (pnlStr) {
          const pnlMatch = String(pnlStr).match(/\$?\s*(-?[\d.]+)/);
          if (pnlMatch) {
            pnl = parseFloat(pnlMatch[1]);
            if (String(pnlStr).match(/^-\$/) || String(pnlStr).match(/^\$-/)) pnl = -Math.abs(pnl);
          }
        }
        let returnAmount = null;
        if (isExit && amount != null && pnl != null) {
          returnAmount = Math.round((amount + pnl) * 100) / 100;
        }
        const orderId = fields["order id"] || null;
        try {
          insertTrade.run(
            timestamp,
            file,
            market,
            null,
            side,
            amount,
            price,
            edge,
            null,
            action,
            status,
            pnl,
            orderId,
            null,
            redact(section.slice(0, 500)),
            returnAmount
          );
          totalCount++;
        } catch {
        }
      }
      upsertIngestState.run(filePath, 0, stats.mtime.toISOString(), 0);
    }
  }
  return totalCount;
}
function ingestScanDetails() {
  if (!import_fs.default.existsSync(SCAN_DETAILS_FILE)) return 0;
  const stats = import_fs.default.statSync(SCAN_DETAILS_FILE);
  const state = getIngestState.get(SCAN_DETAILS_FILE);
  let offset = state?.byte_offset || 0;
  if (stats.size < offset) offset = 0;
  if (stats.size === offset) return 0;
  const fd = import_fs.default.openSync(SCAN_DETAILS_FILE, "r");
  const buffer = Buffer.alloc(stats.size - offset);
  import_fs.default.readSync(fd, buffer, 0, buffer.length, offset);
  import_fs.default.closeSync(fd);
  const lines = buffer.toString("utf-8").split("\n");
  let count = 0;
  const insertMany = db.transaction((rows2) => {
    for (const row of rows2) {
      insertScanDetail.run(
        row.scan_id,
        row.scan_timestamp,
        row.city || null,
        row.market || null,
        row.side || null,
        row.edge ?? null,
        row.price ?? null,
        row.confidence ?? null,
        row.sources || null,
        row.forecast_temp || null,
        row.liquidity ?? null,
        row.rejection_reason || null,
        row.qualified ? 1 : 0
      );
    }
  });
  const rows = [];
  for (const line of lines) {
    if (!line.trim()) continue;
    try {
      const data = JSON.parse(line.trim());
      rows.push(data);
      count++;
    } catch {
    }
  }
  if (rows.length > 0) {
    insertMany(rows);
  }
  upsertIngestState.run(SCAN_DETAILS_FILE, stats.size, stats.mtime.toISOString(), 0);
  return count;
}
function indexWorkspaces() {
  let count = 0;
  function walkDir(dirPath) {
    if (!import_fs.default.existsSync(dirPath)) return;
    let entries;
    try {
      entries = import_fs.default.readdirSync(dirPath, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const fullPath = import_path.default.join(dirPath, entry.name);
      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name)) {
          walkDir(fullPath);
        }
        continue;
      }
      if (!entry.isFile()) continue;
      const ext = import_path.default.extname(entry.name).toLowerCase();
      if (!INDEXABLE_EXT.has(ext)) continue;
      if (isSensitiveFile(entry.name)) continue;
      try {
        const stats = import_fs.default.statSync(fullPath);
        const state = getIngestState.get(fullPath);
        if (state?.last_modified === stats.mtime.toISOString()) continue;
        if (stats.size > 500 * 1024) continue;
        const content = import_fs.default.readFileSync(fullPath, "utf-8");
        const redacted = redact(content);
        try {
          db.prepare("DELETE FROM search_index WHERE source = ?").run(fullPath);
        } catch {
        }
        insertSearch.run(fullPath, redacted, stats.mtime.toISOString());
        upsertIngestState.run(fullPath, 0, stats.mtime.toISOString(), 0);
        count++;
      } catch {
      }
    }
  }
  for (const ws of WORKSPACES) {
    walkDir(ws.path);
  }
  return count;
}
var POLL_INTERVAL_MS = 2e3;
var SEARCH_INDEX_INTERVAL_MS = 3e5;
var lastSearchIndex = 0;
var cycleCount = 0;
function runCycle() {
  const now = Date.now();
  cycleCount++;
  let totalIngested = 0;
  for (const logFile of LOG_FILES) {
    const count = ingestLogFile(logFile.path, logFile.source);
    if (count > 0) {
      console.log(`  [log] ${logFile.source}: +${count} entries`);
      totalIngested += count;
    }
  }
  const eventCount = ingestEvents();
  if (eventCount > 0) {
    console.log(`  [events] +${eventCount} entries`);
    totalIngested += eventCount;
  }
  const tradingUpdated = ingestTradingState();
  if (tradingUpdated) {
    console.log("  [trading] state updated");
  }
  ingestFilledOrders();
  const journalCount = ingestJournals();
  if (journalCount > 0) {
    console.log(`  [journals] +${journalCount} trades`);
    totalIngested += journalCount;
  }
  const scanCount = ingestScanDetails();
  if (scanCount > 0) {
    console.log(`  [scans] +${scanCount} scan details`);
    totalIngested += scanCount;
  }
  if (now - lastSearchIndex > SEARCH_INDEX_INTERVAL_MS) {
    const searchCount = indexWorkspaces();
    if (searchCount > 0 || lastSearchIndex === 0) {
      console.log(`  [search] indexed ${searchCount} files`);
    }
    lastSearchIndex = now;
  }
  if (cycleCount % 30 === 0) {
    const activityCount = db.prepare("SELECT COUNT(*) as c FROM activity").get().c;
    const tradeCount = db.prepare("SELECT COUNT(*) as c FROM trades").get().c;
    const searchCount = db.prepare("SELECT COUNT(*) as c FROM search_index").get().c;
    console.log(`[status] activity: ${activityCount}, trades: ${tradeCount}, search: ${searchCount}`);
  }
}
console.log("Mission Control Watcher starting...");
console.log(`  Database: ${DB_PATH}`);
console.log(`  Logs: ${TINYCLAW_LOGS_DIR}`);
console.log(`  Events: ${TINYCLAW_EVENTS_DIR}`);
console.log(`  Trading: ${TRADING_STATE_FILE}`);
console.log(`  Open Orders: ${OPEN_ORDERS_FILE}`);
console.log(`  Journals: ${JOURNAL_DIR}`);
console.log(`  Poll interval: ${POLL_INTERVAL_MS}ms`);
console.log("");
if (!import_fs.default.existsSync(TRADING_STATE_FILE)) {
  warnMissingFile(TRADING_STATE_FILE, "trading_state.json");
}
if (!import_fs.default.existsSync(OPEN_ORDERS_FILE)) {
  warnMissingFile(OPEN_ORDERS_FILE, "open_orders.json");
}
console.log("Running initial ingestion...");
runCycle();
console.log("Initial ingestion complete.\n");
console.log("Watching for changes...");
var interval = setInterval(runCycle, POLL_INTERVAL_MS);
process.on("SIGINT", () => {
  console.log("\nShutting down watcher...");
  clearInterval(interval);
  db.close();
  process.exit(0);
});
process.on("SIGTERM", () => {
  console.log("\nShutting down watcher...");
  clearInterval(interval);
  db.close();
  process.exit(0);
});
