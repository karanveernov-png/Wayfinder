import { createContext, useCallback, useContext, useMemo, useState, useEffect } from "react";
import { analyseJourney, ApiError, listSavedJourneys, getSavedJourney, deleteSavedJourney, saveJourney } from "../lib/api.js";
import { useAuth } from "./useAuth.js";
import {
  getLocalJourneys,
  addLocalJourney,
  removeLocalJourney,
  updateLocalJourney,
  clearLocalJourneys,
  syncFromSupabase,
  syncToSupabase,
  startPeriodicSync,
  stopPeriodicSync,
  normalizeServerJourney,
  prepareForSave,
  getSyncStatus,
} from "../lib/storage.js";

const JourneyContext = createContext(null);

export function JourneyProvider({ children }) {
  const [journey, setJourney] = useState(null); // last JourneyAnalyseResponse
  const [params, setParams] = useState(null); // { origin, destination, travelMode, demo }
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [savedJourneys, setSavedJourneys] = useState([]);
  const [syncStatus, setSyncStatus] = useState({ total: 0, synced: 0, pending: 0, dirty: 0, isFullySynced: true });
  const { user } = useAuth();

  // Load journeys from localStorage immediately (works offline)
  const loadLocalJourneys = useCallback(async () => {
    try {
      const local = await getLocalJourneys();
      setSavedJourneys(local);
      setSyncStatus(getSyncStatus(local));
    } catch (err) {
      console.error("Failed to load local journeys:", err);
      setSavedJourneys([]);
      setSyncStatus({ total: 0, synced: 0, pending: 0, dirty: 0, isFullySynced: true });
    }
  }, []);

  // Sync with Supabase when user is authenticated and online
  const syncWithServer = useCallback(async () => {
    if (!user) return;

    try {
      // Pull from server first
      const pullResult = await syncFromSupabase(
        { listSavedJourneys, saveJourney, deleteSavedJourney },
        user
      );

      // Then push local changes
      await syncToSupabase(
        { saveJourney, deleteSavedJourney },
        user
      );

      // Refresh local state
      await loadLocalJourneys();
    } catch (err) {
      console.error("Sync with server failed:", err);
      // Don't throw - local data is still available
    }
  }, [user, loadLocalJourneys]);

  // Initial load: localStorage first (instant), then sync with server
  useEffect(() => {
    loadLocalJourneys();

    // If user is authenticated, start syncing with server
    if (user) {
      syncWithServer();

      // Start periodic background sync
      const stopSync = startPeriodicSync(
        { listSavedJourneys, saveJourney, deleteSavedJourney },
        user
      );

      return () => {
        stopSync();
        stopPeriodicSync();
      };
    } else {
      // User signed out - clear local journeys
      clearLocalJourneys();
      setSavedJourneys([]);
    }
  }, [user, loadLocalJourneys, syncWithServer]);

  const runAnalysis = useCallback(async (requestParams) => {
    setLoading(true);
    setError(null);
    try {
      const result = await analyseJourney(requestParams);
      setJourney(result);
      setParams(requestParams);
      return result;
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Something went wrong while planning that journey.";
      setError(message);
      setJourney(null);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const applyJourneyResult = useCallback((result, requestParams) => {
    setJourney(result);
    setParams(requestParams);
    setError(null);
  }, []);

  const saveCurrentJourney = useCallback(async () => {
    if (!journey || !params) return null;

    const entry = {
      origin: journey.journey.origin.display_name || journey.journey.origin.query,
      destination: journey.journey.destination.display_name || journey.journey.destination.query,
      distance_km: journey.journey.distance_km,
      duration_minutes: journey.journey.duration_minutes,
      risk_level: journey.risk_assessment?.level || "unknown",
      data_status_mode: journey.data_status?.mode || "unknown",
      journey_json: journey,
      params_json: params,
    };

    try {
      // Always save locally first (works offline)
      const localJourney = {
        ...entry,
        id: `local-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        synced: false,
        dirty: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      await addLocalJourney(localJourney);
      await loadLocalJourneys();

      // If authenticated, also save to server
      if (user) {
        try {
          const saved = await saveJourney(prepareForSave(localJourney));

          // Update local entry with server ID and mark as synced
          await updateLocalJourney(localJourney.id, {
            id: saved.id,
            synced: true,
            dirty: false,
          });
          await loadLocalJourneys();

          return saved;
        } catch (serverErr) {
          // Server save failed - keep local copy, will retry on next sync
          console.warn("Server save failed, saved locally:", serverErr);
          setError("Saved locally. Will sync when online.");
          return localJourney;
        }
      }

      return localJourney;
    } catch (err) {
      const message = err.message || "Failed to save journey";
      setError(message);
      throw err;
    }
  }, [journey, params, user, loadLocalJourneys]);

  const removeSavedJourney = useCallback(async (id) => {
    try {
      // Remove locally first (instant UI update)
      await removeLocalJourney(id);
      await loadLocalJourneys();

      // If it was a synced journey, also delete from server
      const journeyToDelete = savedJourneys.find(j => j.id === id);
      if (user && journeyToDelete?.synced) {
        try {
          await deleteSavedJourney(id);
        } catch (serverErr) {
          console.warn("Server delete failed, will retry on sync:", serverErr);
          // Re-add locally with dirty flag for retry
          await addLocalJourney({ ...journeyToDelete, dirty: true, deleted: true });
          await loadLocalJourneys();
        }
      }
    } catch (err) {
      setError(err.message || "Failed to delete journey");
      throw err;
    }
  }, [savedJourneys, user, loadLocalJourneys]);

  const loadSavedJourney = useCallback(async (id) => {
    // First check local storage
    const localJourneys = await getLocalJourneys();
    const localEntry = localJourneys.find(j => j.id === id);

    if (localEntry) {
      setJourney(localEntry.journey_json);
      setParams(localEntry.params_json);
      return localEntry;
    }

    // Fallback to server if authenticated
    if (user) {
      try {
        const entry = await getSavedJourney(id);
        if (!entry) return null;
        setJourney(entry.journey_json);
        setParams(entry.params_json);
        return entry;
      } catch (err) {
        setError(err.message || "Failed to load journey");
        throw err;
      }
    }

    return null;
  }, [user]);

  const clearJourney = useCallback(() => {
    setJourney(null);
    setParams(null);
    setError(null);
  }, []);

  const retrySync = useCallback(async () => {
    if (user) {
      await syncWithServer();
    }
  }, [user, syncWithServer]);

  const value = useMemo(
    () => ({
      journey,
      params,
      loading,
      error,
      savedJourneys,
      syncStatus,
      runAnalysis,
      applyJourneyResult,
      saveCurrentJourney,
      removeSavedJourney,
      loadSavedJourney,
      clearJourney,
      retrySync,
      isOnline: typeof navigator !== 'undefined' && navigator.onLine,
    }),
    [
      journey,
      params,
      loading,
      error,
      savedJourneys,
      syncStatus,
      runAnalysis,
      applyJourneyResult,
      saveCurrentJourney,
      removeSavedJourney,
      loadSavedJourney,
      clearJourney,
      retrySync,
      user,
    ]
  );

  return <JourneyContext.Provider value={value}>{children}</JourneyContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components -- hook is tightly coupled to the provider above, kept in one file on purpose
export function useJourney() {
  const ctx = useContext(JourneyContext);
  if (!ctx) throw new Error("useJourney must be used within a JourneyProvider");
  return ctx;
}