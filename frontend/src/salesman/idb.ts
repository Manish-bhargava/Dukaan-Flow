/**
 * Tiny promise wrapper over IndexedDB (persistent, survives closing the app and restarting
 * the phone). Stores:
 *   kv      key -> value   (downloaded bundle, cached order history)
 *   orders  client_order_id -> LocalOrder   (the offline outbox; never deleted silently)
 *   visits  id -> LocalVisit
 */
const DB_NAME = 'dukaanflow-salesman'
const VERSION = 1

let dbPromise: Promise<IDBDatabase> | null = null

function open(): Promise<IDBDatabase> {
  dbPromise ??= new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains('kv')) db.createObjectStore('kv')
      if (!db.objectStoreNames.contains('orders')) db.createObjectStore('orders', { keyPath: 'client_order_id' })
      if (!db.objectStoreNames.contains('visits')) db.createObjectStore('visits', { keyPath: 'id' })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  return dbPromise
}

type Store = 'kv' | 'orders' | 'visits'

async function run<T>(store: Store, mode: IDBTransactionMode, op: (s: IDBObjectStore) => IDBRequest): Promise<T> {
  const db = await open()
  return new Promise<T>((resolve, reject) => {
    const tx = db.transaction(store, mode)
    const request = op(tx.objectStore(store))
    tx.oncomplete = () => resolve(request.result as T)
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  })
}

export const idbGet = <T>(store: Store, key: string) => run<T | undefined>(store, 'readonly', (s) => s.get(key))
export const idbAll = <T>(store: Store) => run<T[]>(store, 'readonly', (s) => s.getAll())
export const idbPut = (store: Store, value: unknown, key?: string) =>
  run<IDBValidKey>(store, 'readwrite', (s) => (key === undefined ? s.put(value) : s.put(value, key)))
export const idbDelete = (store: Store, key: string) => run<undefined>(store, 'readwrite', (s) => s.delete(key))
