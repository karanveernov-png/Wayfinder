import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Compass,
  Route,
  MapPin,
  CloudSun,
  Bookmark,
  Navigation,
  Menu,
  PanelLeftClose,
  TriangleAlert,
} from "lucide-react";
import { checkHealth } from "../../lib/api.js";
import { useJourney } from "../../context/JourneyContext.jsx";
import DataStatusBadge from "../journey/DataStatusBadge.jsx";
import SidebarProfile from "./SidebarProfile.jsx";

const navigation = [
  { label: "Overview", path: "/", icon: Compass },
  { label: "Trip Planner", path: "/trip-planner", icon: Route },
  { label: "Nearby Places", path: "/nearby-places", icon: MapPin },
  { label: "Travel Insights", path: "/travel-insights", icon: CloudSun },
  { label: "Saved Journeys", path: "/saved-journeys", icon: Bookmark },
];

/** Longest-matching nav entry for the current path — "/" only matches itself. */
function activeNavLabel(pathname) {
  const match = navigation
    .filter((item) => (item.path === "/" ? pathname === "/" : pathname.startsWith(item.path)))
    .sort((a, b) => b.path.length - a.path.length)[0];
  return match?.label || "Waymark";
}

/** One health check, shared by the header badge and the sidebar status row below. */
function useBackendStatus() {
  const [status, setStatus] = useState("checking"); // checking | online | offline
  useEffect(() => {
    let cancelled = false;
    checkHealth()
      .then(() => !cancelled && setStatus("online"))
      .catch(() => !cancelled && setStatus("offline"));
    return () => {
      cancelled = true;
    };
  }, []);
  return status;
}

function BackendStatusBadge({ status }) {
  if (status === "checking") {
    return (
      <span className="rounded-full bg-slate-100 px-3 py-2 text-xs font-medium text-slate-500">
        Checking backend…
      </span>
    );
  }
  if (status === "offline") {
    return (
      <span
        className="rounded-full bg-red-50 px-3 py-2 text-xs font-medium text-red-700"
        title="Start the backend or check VITE_API_BASE_URL"
      >
        Backend unreachable
      </span>
    );
  }
  return (
    <span className="rounded-full bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700">
      Backend connected
    </span>
  );
}

export default function AppLayout() {
  const { journey } = useJourney();
  const location = useLocation();
  const backendStatus = useBackendStatus();
  const bhuvanRouteSource = journey?.data_status?.sources?.find(
    (source) => source.name === "isro-bhuvan-routing",
  );
  const backupRouteSource = journey?.data_status?.sources?.find(
    (source) => source.name === "osrm-routing" && source.detail?.includes("Backup routing used"),
  );
  const [isDesktop, setIsDesktop] = useState(() =>
    window.matchMedia("(min-width: 768px)").matches,
  );
  const [desktopSidebarOpen, setDesktopSidebarOpen] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(min-width: 768px)");
    const handleChange = (event) => setIsDesktop(event.matches);
    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, []);

  return (
    <div className="relative min-h-screen bg-[#F7F8FA] text-slate-800 md:flex">
      {mobileSidebarOpen && (
        <button
          type="button"
          aria-label="Close sidebar"
          onClick={() => setMobileSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-slate-950/40 md:hidden"
        />
      )}
      <aside
        id="app-sidebar"
        className={`fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white p-6 transition-transform duration-200 md:static md:z-auto md:translate-x-0 ${
          mobileSidebarOpen ? "translate-x-0" : "-translate-x-full"
        } ${desktopSidebarOpen ? "md:flex" : "md:hidden"}`}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#203C5A] text-white">
            <Navigation size={21} />
          </div>
          <div>
            <h1 className="text-xl font-bold">waymark</h1>
            <p className="text-xs text-slate-500">Travel intelligence</p>
          </div>
        </div>

        <p className="mb-3 mt-10 text-xs font-semibold uppercase tracking-widest text-slate-400">
          Workspace
        </p>

        <nav className="space-y-1">
          {navigation.map(({ label, path, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              onClick={() => setMobileSidebarOpen(false)}
              className={({ isActive }) =>
                `group relative flex items-center gap-3 rounded-lg py-3 pl-3.5 pr-3 text-sm transition-all duration-150 ${
                  isActive
                    ? "bg-[#EAF0F6] font-semibold text-[#203C5A]"
                    : "text-slate-600 hover:translate-x-0.5 hover:bg-slate-50"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={`absolute inset-y-1.5 left-0 w-[3px] rounded-full bg-[#203C5A] transition-all duration-150 ${
                      isActive ? "opacity-100" : "scale-y-0 opacity-0 group-hover:scale-y-50 group-hover:opacity-40"
                    }`}
                    aria-hidden="true"
                  />
                  <Icon
                    size={18}
                    className={`transition-transform duration-150 ${isActive ? "" : "group-hover:scale-110"}`}
                  />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto rounded-xl border border-slate-200 p-3.5">
          <p className="eyebrow-tight">System status</p>
          <div className="mt-2 flex items-center gap-2 text-sm">
            <span
              className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                backendStatus === "online"
                  ? "bg-emerald-500"
                  : backendStatus === "offline"
                    ? "bg-red-500"
                    : "bg-slate-300"
              }`}
              aria-hidden="true"
            />
            <span className="text-slate-700">
              {backendStatus === "online"
                ? "API connected"
                : backendStatus === "offline"
                  ? "API unreachable"
                  : "Checking API…"}
            </span>
          </div>
          {journey?.data_status?.mode && (
            <div className="mt-1.5 flex items-center gap-2 text-sm">
              <span
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                  journey.data_status.mode === "live"
                    ? "bg-emerald-500"
                    : journey.data_status.mode === "degraded"
                      ? "bg-red-500"
                      : "bg-amber-500"
                }`}
                aria-hidden="true"
              />
              <span className="text-slate-700">
                Last journey: {journey.data_status.mode}
              </span>
            </div>
          )}
        </div>

        <SidebarProfile />
      </aside>

      <div className="min-w-0 flex-1">
        <header className="flex h-[76px] items-center justify-between border-b border-slate-200 bg-white px-5 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              aria-label="Toggle sidebar"
              aria-controls="app-sidebar"
              aria-expanded={isDesktop ? desktopSidebarOpen : mobileSidebarOpen}
              onClick={() => {
                if (isDesktop) {
                  setDesktopSidebarOpen((open) => !open);
                } else {
                  setMobileSidebarOpen((open) => !open);
                }
              }}
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-slate-600 transition hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#203C5A]"
            >
              <Menu className="md:hidden" size={20} aria-hidden="true" />
              <PanelLeftClose className="hidden md:block" size={20} aria-hidden="true" />
            </button>
            <div className="min-w-0">
              <p className="text-sm text-slate-500">Waymark workspace</p>
              <h2 className="text-lg font-semibold">{activeNavLabel(location.pathname)}</h2>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {journey && <DataStatusBadge mode={journey.data_status?.mode} />}
            <BackendStatusBadge status={backendStatus} />
          </div>
        </header>

        {backupRouteSource && (
          <div
            className="flex items-start gap-3 border-b border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-900 sm:px-8"
            role="status"
          >
            <TriangleAlert size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
            <p>
              <span className="font-semibold">Backup routing is being used.</span>{" "}
              {bhuvanRouteSource?.detail || backupRouteSource.detail}
            </p>
          </div>
        )}

        <Outlet />
      </div>
    </div>
  );
}
