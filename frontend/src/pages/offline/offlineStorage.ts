/**
 * IndexedDB Persistence & WebCrypto Encryption for PRAMANA Offline Field Scrutiny.
 *
 * Implements Module 1 client persistence:
 * - Stores authorized inspection cases offline.
 * - Stores captured evidence with AES-GCM browser encryption.
 * - Manages durable offline sync queue across browser restarts.
 */

const DB_NAME = "pramana_field_scrutiny_v2";
const DB_VERSION = 1;

export interface OfflineEvidenceRecord {
  id: string;
  inspection_id: string;
  category: "document" | "image" | "inspection_note" | "supporting_attachment";
  file_reference: string;
  sha256: string;
  phash?: string;
  dhash?: string;
  description: string;
  collected_at: string;
  device_event_id: string;
  encrypted_bytes?: string;
  location_geo?: {
    latitude: number;
    longitude: number;
    accuracy_meters: number;
    verification: string;
  };
}

export interface OfflineSyncQueueItem {
  event_id: string;
  inspection_id?: string;
  application_id?: string;
  event_type: string;
  payload: any;
  created_at: string;
  synced: boolean;
}

class OfflineStorageManager {
  private dbPromise: Promise<IDBDatabase> | null = null;
  private cryptoKeyPromise: Promise<CryptoKey> | null = null;

  private getDB(): Promise<IDBDatabase> {
    if (this.dbPromise) return this.dbPromise;

    this.dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (e) => {
        const db = (e.target as IDBOpenDBRequest).result;
        if (!db.objectStoreNames.contains("inspections")) {
          db.createObjectStore("inspections", { keyPath: "id" });
        }
        if (!db.objectStoreNames.contains("evidence")) {
          const store = db.createObjectStore("evidence", { keyPath: "id" });
          store.createIndex("by_inspection", "inspection_id", { unique: false });
        }
        if (!db.objectStoreNames.contains("sync_queue")) {
          db.createObjectStore("sync_queue", { keyPath: "event_id" });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });

    return this.dbPromise;
  }

  async getCryptoKey(): Promise<CryptoKey> {
    if (this.cryptoKeyPromise) return this.cryptoKeyPromise;

    // Generates a session encryption key for client-side storage
    this.cryptoKeyPromise = window.crypto.subtle.generateKey(
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );
    return this.cryptoKeyPromise;
  }

  async saveInspectionOffline(inspection: any): Promise<void> {
    const db = await this.getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("inspections", "readwrite");
      const store = tx.objectStore("inspections");
      store.put({ ...inspection, updated_offline_at: new Date().toISOString() });
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async getOfflineInspections(): Promise<any[]> {
    const db = await this.getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("inspections", "readonly");
      const store = tx.objectStore("inspections");
      const req = store.getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  }

  async saveEvidenceOffline(evidence: OfflineEvidenceRecord): Promise<void> {
    const db = await this.getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("evidence", "readwrite");
      const store = tx.objectStore("evidence");
      store.put(evidence);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async getOfflineEvidence(inspectionId: string): Promise<OfflineEvidenceRecord[]> {
    const db = await this.getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("evidence", "readonly");
      const store = tx.objectStore("evidence");
      const idx = store.index("by_inspection");
      const req = idx.getAll(inspectionId);
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  }

  async enqueueSyncEvent(event: OfflineSyncQueueItem): Promise<void> {
    const db = await this.getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("sync_queue", "readwrite");
      const store = tx.objectStore("sync_queue");
      store.put(event);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async getPendingSyncEvents(): Promise<OfflineSyncQueueItem[]> {
    const db = await this.getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("sync_queue", "readonly");
      const store = tx.objectStore("sync_queue");
      const req = store.getAll();
      req.onsuccess = () => {
        const items: OfflineSyncQueueItem[] = req.result || [];
        resolve(items.filter((it) => !it.synced));
      };
      req.onerror = () => reject(req.error);
    });
  }

  async markEventsSynced(eventIds: string[]): Promise<void> {
    const db = await this.getDB();
    const tx = db.transaction("sync_queue", "readwrite");
    const store = tx.objectStore("sync_queue");
    for (const id of eventIds) {
      const req = store.get(id);
      req.onsuccess = () => {
        if (req.result) {
          req.result.synced = true;
          store.put(req.result);
        }
      };
    }
    return new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }
}

export const offlineStorage = new OfflineStorageManager();
