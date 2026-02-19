import Database from 'better-sqlite3';
import { DB_PATH } from './paths';
import { initSchema } from './schema';
import path from 'path';
import fs from 'fs';

// Ensure the directory exists
fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });

const db = new Database(DB_PATH);

// Performance settings for local use
db.pragma('journal_mode = WAL');
db.pragma('synchronous = NORMAL');
db.pragma('foreign_keys = ON');

// Initialize schema on first import
initSchema(db);

export default db;
