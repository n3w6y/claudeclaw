import path from 'path';
import os from 'os';

const HOME = os.homedir();

// TinyClaw logs
export const TINYCLAW_LOGS_DIR = path.join(HOME, '.tinyclaw', 'logs');
export const TINYCLAW_EVENTS_DIR = path.join(HOME, '.tinyclaw', 'events');

// Log files to watch
export const LOG_FILES = [
  { path: path.join(TINYCLAW_LOGS_DIR, 'daemon.log'), source: 'daemon.log' },
  { path: path.join(TINYCLAW_LOGS_DIR, 'queue.log'), source: 'queue.log' },
  { path: path.join(TINYCLAW_LOGS_DIR, 'telegram.log'), source: 'telegram.log' },
  { path: path.join(TINYCLAW_LOGS_DIR, 'heartbeat.log'), source: 'heartbeat.log' },
];

// Trading data
export const TRADER_BASE = path.join(HOME, 'claudeclaw', 'trader', 'polymarket-trader');
export const TRADING_STATE_FILE = path.join(TRADER_BASE, 'trading_state.json');
export const OPEN_ORDERS_FILE = path.join(TRADER_BASE, 'open_orders.json');
export const JOURNAL_DIR = path.join(TRADER_BASE, 'journal');
export const FORECAST_CACHE = path.join(TRADER_BASE, 'cache', 'forecasts.json');

// Agent workspaces (for search indexing)
export const WORKSPACES = [
  { path: path.join(HOME, 'claudeclaw', 'elliot'), agent: 'elliot' },
  { path: path.join(HOME, 'claudeclaw', 'trader'), agent: 'trader' },
  { path: path.join(HOME, 'claudeclaw', 'dev'), agent: 'dev' },
];

// SQLite database
export const DB_PATH = path.join(HOME, 'claudeclaw', 'mission-control', 'data.db');

// Files to skip during search indexing
export const SKIP_DIRS = ['node_modules', '__pycache__', '.git', '.next', '.cache', 'cache'];
export const SKIP_FILES = ['.env', 'credentials', 'secrets', '.key', '.pem'];
export const INDEXABLE_EXTENSIONS = ['.md', '.py', '.json', '.ts', '.tsx', '.js', '.sh', '.txt', '.log'];
