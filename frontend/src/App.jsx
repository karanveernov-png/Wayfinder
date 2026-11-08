import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import TripPlannerPage from "./pages/TripPlannerPage.jsx";
import NearbyPlacesPage from "./pages/NearbyPlacespage.jsx";
import TravelInsightsPage from "./pages/TravelInsightsPage.jsx";
import SavedJourneysPage from "./pages/SavedJourneypage.jsx";
import NotFoundPage from "./pages/NotFoundPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import { JourneyProvider } from "./context/JourneyContext.jsx";
import { AuthProvider } from "./context/AuthContext.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import ConfigErrorScreen from "./components/ConfigErrorScreen.jsx";
import ProtectedRoute from "./components/auth/ProtectedRoute.jsx";
import { isSupabaseConfigured } from "./lib/supabase.js";

export default function App() {
  // Checked before AuthProvider mounts: AuthProvider calls supabase.auth.*
  // on mount, which would throw if supabase is null (see lib/supabase.js).
  // AuthProvider wraps <ErrorBoundary> below, not the other way around, so
  // a throw here would not be caught by it — this check is what actually
  // prevents the blank-white-page failure mode in that case.
  if (!isSupabaseConfigured) {
    const missing = [];
    if (!import.meta.env.VITE_SUPABASE_URL) missing.push("VITE_SUPABASE_URL");
    if (!import.meta.env.VITE_SUPABASE_ANON_KEY) missing.push("VITE_SUPABASE_ANON_KEY");
    return <ConfigErrorScreen missing={missing} />;
  }

  return (
    <AuthProvider>
      <JourneyProvider>
        <BrowserRouter>
          <ErrorBoundary>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
                <Route path="/" element={<OverviewPage />} />
                <Route path="/trip-planner" element={<TripPlannerPage />} />
                <Route path="/nearby-places" element={<NearbyPlacesPage />} />
                <Route path="/travel-insights" element={<TravelInsightsPage />} />
                <Route path="/saved-journeys" element={<SavedJourneysPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Route>
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </ErrorBoundary>
        </BrowserRouter>
      </JourneyProvider>
    </AuthProvider>
  );
}
