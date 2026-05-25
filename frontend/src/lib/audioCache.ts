/**
 * IndexedDB-backed audio cache.
 * - TTS blobs are stored so the same text never hits the API twice.
 * - User recordings are stored keyed by session+question so the user can replay what they said.
 * Falls back silently if IndexedDB is unavailable (private browsing etc.).
 */

const DB_NAME = 'hireforge_audio_v1';
const DB_VER  = 1;
const TTS_STORE = 'tts';
const REC_STORE = 'recordings';

let _db: IDBDatabase | null = null;

async function getDb(): Promise<IDBDatabase | null> {
  if (_db) return _db;
  if (typeof indexedDB === 'undefined') return null;
  return new Promise(resolve => {
    try {
      const req = indexedDB.open(DB_NAME, DB_VER);
      req.onupgradeneeded = (e) => {
        const db = (e.target as IDBOpenDBRequest).result;
        if (!db.objectStoreNames.contains(TTS_STORE))  db.createObjectStore(TTS_STORE);
        if (!db.objectStoreNames.contains(REC_STORE))  db.createObjectStore(REC_STORE);
      };
      req.onsuccess  = (e) => { _db = (e.target as IDBOpenDBRequest).result; resolve(_db); };
      req.onerror    = () => resolve(null);
    } catch { resolve(null); }
  });
}

function dbGet(store: string, key: string): Promise<Blob | null> {
  return getDb().then(db => {
    if (!db) return null;
    return new Promise(resolve => {
      try {
        const req = db.transaction(store, 'readonly').objectStore(store).get(key);
        req.onsuccess = () => resolve((req.result as Blob) ?? null);
        req.onerror   = () => resolve(null);
      } catch { resolve(null); }
    });
  });
}

function dbPut(store: string, key: string, blob: Blob): Promise<void> {
  return getDb().then(db => {
    if (!db) return;
    return new Promise<void>(resolve => {
      try {
        const tx = db.transaction(store, 'readwrite');
        tx.objectStore(store).put(blob, key);
        tx.oncomplete = () => resolve();
        tx.onerror    = () => resolve();
      } catch { resolve(); }
    });
  });
}

/** Stable hash key for a TTS request. */
export function ttsKey(text: string, voice: string, speed: number): string {
  const s = `${voice}|${speed.toFixed(2)}|${text}`;
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return Math.abs(h).toString(36);
}

/** Key for a user recording: session + question index. */
export function recKey(sessionId: number | null, qIdx: number): string {
  return `s${sessionId ?? 0}_q${qIdx}`;
}

export const getTTSCache   = (key: string)              => dbGet(TTS_STORE, key);
export const setTTSCache   = (key: string, b: Blob)     => dbPut(TTS_STORE, key, b);
export const getUserRec    = (key: string)              => dbGet(REC_STORE, key);
export const saveUserRec   = (key: string, b: Blob)     => dbPut(REC_STORE, key, b);
