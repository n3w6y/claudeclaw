import type Database from 'better-sqlite3';

export function initSchema(db: Database.Database) {
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

    CREATE TABLE IF NOT EXISTS balance_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp TEXT NOT NULL,
      balance REAL NOT NULL,
      event TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_balance_history_ts ON balance_history(timestamp);
  `);

  // FTS5 virtual table for search — separate try since it fails if already exists
  try {
    db.exec(`
      CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
        source,
        content,
        timestamp
      );
    `);
  } catch {
    // FTS5 table already exists or not supported
  }
}
