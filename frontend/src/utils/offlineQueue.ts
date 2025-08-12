const DB_NAME = 'reportQueue';
const STORE = 'reports';

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function complete(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function queueReport(data: any) {
  const db = await openDB();
  const tx = db.transaction(STORE, 'readwrite');
  tx.objectStore(STORE).add({ data });
  await complete(tx);
  db.close();
}

export async function flushQueue() {
  const db = await openDB();
  const tx = db.transaction(STORE, 'readwrite');
  const store = tx.objectStore(STORE);
  const items: any[] = await new Promise(res => {
    const req = store.getAll();
    req.onsuccess = () => res(req.result);
  });
  for (const item of items) {
    try {
      await fetch('/reports', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item.data)
      });
      store.delete(item.id);
    } catch (e) {
      // keep item for retry
    }
  }
  await complete(tx);
  db.close();
}

if (typeof window !== 'undefined') {
  window.addEventListener('online', flushQueue);
}
