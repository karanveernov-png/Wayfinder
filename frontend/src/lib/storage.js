/**
 * Hybrid storage for saved journeys with offline support.
 *
 * Strategy:
 * - localStorage is the source of truth for offline/initial load
 * - Supabase is the cloud sync target when online & authenticated
 * - On load: read from localStorage immediately (instant UI)
 * - On save: write to localStorage first (instant), then sync to Supabase
 * - On delete: remove from localStorage first, then sync to Supabase
 * - Periodic sync attempt when online (simple polling)
 */

const STORAGE_KEY = 'wayfinder_saved_journeys';
const SYNC_INTERVAL_MS = 30000; // 30 seconds

// In-memory cache for fast access
let memoryCache = null;
let syncTimer = null;

/**
 * Get all saved journeys from localStorage
 */
export function getLocalJourneys() {
  if (memoryCache !== null) {
    return Promise.resolve([...memoryCache]);
  }

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    const journeys = stored ? JSON.parse(stored) : [];
    memoryCache = journeys;
    return Promise.resolve([...journeys]);
  } catch (e) {
    console.error('Failed to read saved journeys from localStorage:', e);
    return Promise.resolve([]);
  }
}

/**
 * Save journeys to localStorage
 */
export function setLocalJourneys(journeys) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(journeys));
    memoryCache = [...journeys];
    return Promise.resolve();
  } catch (e) {
    console.error('Failed to save journeys to localStorage:', e);
    return Promise.reject(e);
  }
}

/**
 * Add a single journey to localStorage
 */
export async function addLocalJourney(journey) {
  const journeys = await getLocalJourneys();
  // Avoid duplicates by ID
  const exists = journeys.some(j => j.id === journey.id);
  if (!exists) {
    journeys.unshift(journey); // Add to front (most recent first)
    await setLocalJourneys(journeys);
  }
  return journey;
}

/**
 * Remove a journey from localStorage
 */
export async function removeLocalJourney(id) {
  const journeys = await getLocalJourneys();
  const filtered = journeys.filter(j => j.id !== id);
  await setLocalJourneys(filtered);
}

/**
 * Update a journey in localStorage (for sync status, etc.)
 */
export async function updateLocalJourney(id, updates) {
  const journeys = await getLocalJourneys();
  const index = journeys.findIndex(j => j.id === id);
  if (index !== -1) {
    journeys[index] = { ...journeys[index], ...updates };
    await setLocalJourneys(journeys);
  }
}

/**
 * Clear all local journeys (e.g., on sign out)
 */
export function clearLocalJourneys() {
  try {
    localStorage.removeItem(STORAGE_KEY);
    memoryCache = null;
    return Promise.resolve();
  } catch (e) {
    console.error('Failed to clear local journeys:', e);
    return Promise.reject(e);
  }
}

/**
 * Check if we're likely online (simple navigator.onLine check)
 * Note: navigator.onLine is not 100% reliable but good enough for this use case
 */
export function isOnline() {
  return typeof navigator !== 'undefined' && navigator.onLine;
}

/**
 * Sync local journeys to Supabase
 * Returns { synced: number, failed: number }
 */
export async function syncToSupabase(api, user) {
  if (!user || !isOnline()) {
    return { synced: 0, failed: 0, reason: 'offline_or_unauthenticated' };
  }

  const localJourneys = await getLocalJourneys();
  // Only sync journeys that don't have a Supabase ID yet (synced: false)
  // or that were modified locally
  const toSync = localJourneys.filter(j => !j.synced || j.dirty);

  if (toSync.length === 0) {
    return { synced: 0, failed: 0, reason: 'nothing_to_sync' };
  }

  let synced = 0;
  let failed = 0;

  for (const journey of toSync) {
    try {
      // Prepare data for Supabase (exclude local-only fields)
      const { id, synced: _syncedFlag, dirty, ...supabaseData } = journey;
      const saved = await api.saveJourney(supabaseData);

      // Update local copy with Supabase ID and mark as synced
      await updateLocalJourney(id, {
        id: saved.id, // Replace local ID with Supabase UUID
        synced: true,
        dirty: false,
      });

      synced++;
    } catch (err) {
      console.error('Failed to sync journey to Supabase:', err);
      // Mark as dirty for retry
      await updateLocalJourney(journey.id, { dirty: true });
      failed++;
    }
  }

  return { synced, failed };
}

/**
 * Fetch journeys from Supabase and merge with local
 * - Local journeys that are already synced are kept
 * - New journeys from Supabase are added to localStorage
 */
export async function syncFromSupabase(api, user) {
  if (!user || !isOnline()) {
    return { fetched: 0, merged: 0, reason: 'offline_or_unauthenticated' };
  }

  try {
    const serverJourneys = await api.listSavedJourneys();
    const localJourneys = await getLocalJourneys();

    // Build a map of local journeys by their Supabase ID (if synced)
    const localByServerId = new Map();
    const unsyncedLocal = [];

    for (const j of localJourneys) {
      if (j.synced && j.id) {
        localByServerId.set(j.id, j);
      } else {
        unsyncedLocal.push(j);
      }
    }

    // Merge server journeys
    let merged = 0;
    for (const serverJourney of serverJourneys) {
      if (!localByServerId.has(serverJourney.id)) {
        // New journey from server - add to local
        await addLocalJourney({
          ...serverJourney,
          synced: true,
          dirty: false,
        });
        merged++;
      }
    }

    return { fetched: serverJourneys.length, merged };
  } catch (err) {
    console.error('Failed to fetch journeys from Supabase:', err);
    return { fetched: 0, merged: 0, reason: 'error', error: err };
  }
}

/**
 * Full bidirectional sync
 */
export async function fullSync(api, user) {
  const pushResult = await syncToSupabase(api, user);
  const pullResult = await syncFromSupabase(api, user);
  return { push: pushResult, pull: pullResult };
}

/**
 * Start periodic background sync
 */
export function startPeriodicSync(api, user) {
  stopPeriodicSync();

  const doSync = async () => {
    if (user && isOnline()) {
      await fullSync(api, user);
    }
  };

  // Initial sync
  doSync();

  // Periodic sync
  syncTimer = setInterval(doSync, SYNC_INTERVAL_MS);

  // Also sync when coming online
  if (typeof window !== 'undefined') {
    window.addEventListener('online', doSync);
  }

  return () => stopPeriodicSync();
}

/**
 * Stop periodic background sync
 */
export function stopPeriodicSync() {
  if (syncTimer) {
    clearInterval(syncTimer);
    syncTimer = null;
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('online', startPeriodicSync);
  }
}

/**
 * Get sync status for UI display
 */
export function getSyncStatus(journeys) {
  const total = journeys.length;
  const synced = journeys.filter(j => j.synced).length;
  const pending = journeys.filter(j => !j.synced).length;
  const dirty = journeys.filter(j => j.dirty).length;

  return {
    total,
    synced,
    pending,
    dirty,
    isFullySynced: pending === 0 && dirty === 0,
  };
}

/**
 * Convert a local journey (with local ID) to the format expected by API
 * when saving for the first time
 */
export function prepareForSave(localJourney) {
  const { id, synced, dirty, ...rest } = localJourney;
  return rest;
}

/**
 * Convert server journey to local format
 */
export function normalizeServerJourney(serverJourney) {
  return {
    ...serverJourney,
    synced: true,
    dirty: false,
  };
}