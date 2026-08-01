import Database from 'better-sqlite3';
import path from 'path';

let localDb = null;

export function getDb(runtime) {
  // If running on Cloudflare (with D1 binding)
  if (runtime?.env?.DB) {
    return runtime.env.DB;
  }
  
  // Otherwise, fall back to local better-sqlite3 database
  if (!localDb) {
    const dbPath = path.resolve(process.cwd(), 'pSEO.db');
    localDb = new Database(dbPath, { readonly: true });
  }
  
  // Wrap local better-sqlite3 in a D1-compatible async interface
  return {
    prepare(sql) {
      const stmt = localDb.prepare(sql);
      return {
        bind(...params) {
          return {
            async all() {
              try {
                const results = stmt.all(...params);
                return { results, success: true };
              } catch (e) {
                console.error("Local DB all() error:", e);
                return { results: [], success: false, error: e.message };
              }
            },
            async first(columnName) {
              try {
                const row = stmt.get(...params);
                if (row && columnName) {
                  return row[columnName];
                }
                return row;
              } catch (e) {
                console.error("Local DB first() error:", e);
                return null;
              }
            },
            async run() {
              try {
                const res = stmt.run(...params);
                return { success: true, meta: res };
              } catch (e) {
                return { success: false, error: e.message };
              }
            }
          };
        },
        async all() {
          try {
            const results = stmt.all();
            return { results, success: true };
          } catch (e) {
            return { results: [], success: false, error: e.message };
          }
        },
        async first(columnName) {
          try {
            const row = stmt.get();
            if (row && columnName) {
              return row[columnName];
            }
            return row;
          } catch (e) {
            return null;
          }
        },
        async run() {
          try {
            const res = stmt.run();
            return { success: true, meta: res };
          } catch (e) {
            return { success: false, error: e.message };
          }
        }
      };
    }
  };
}

export default getDb;
