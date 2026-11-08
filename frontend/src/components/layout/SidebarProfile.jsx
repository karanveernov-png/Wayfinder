import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { LogOut, Settings, UserRound } from "lucide-react";
import { useAuth } from "../../context/useAuth.js";

function getDisplayName(user) {
  return user?.user_metadata?.full_name?.trim()
    || user?.user_metadata?.name?.trim()
    || "";
}

export default function SidebarProfile() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState("");

  const email = user?.email || "";
  const name = getDisplayName(user);
  const avatarLetter = (name || email || "A").charAt(0).toUpperCase();

  async function handleSignOut() {
    setError("");
    setSigningOut(true);
    try {
      const { error: signOutError } = await signOut();
      if (signOutError) throw signOutError;
      navigate("/login", { replace: true });
    } catch (signOutError) {
      setError(signOutError.message || "Unable to log out. Please try again.");
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div className="relative mt-4 border-t border-slate-200 pt-4">
      {menuOpen && (
        <div
          id="sidebar-profile-menu"
          className="absolute bottom-full left-0 z-20 mb-2 w-full rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg"
          role="menu"
          aria-label="Account options"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setMenuOpen(false);
              navigate("/settings");
            }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50"
          >
            <Settings size={16} />
            Settings
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={handleSignOut}
            disabled={signingOut}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm text-red-700 hover:bg-red-50 disabled:opacity-60"
          >
            <LogOut size={16} />
            {signingOut ? "Logging out…" : "Log out"}
          </button>
          {error && <p className="px-3 py-2 text-xs text-red-700" role="alert">{error}</p>}
        </div>
      )}

      <button
        type="button"
        aria-label="Open account options"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        aria-controls="sidebar-profile-menu"
        onClick={() => {
          setMenuOpen(!menuOpen);
          setError("");
        }}
        className="flex w-full items-center gap-3 rounded-xl p-2 text-left transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#203C5A]"
      >
        <span
          aria-hidden="true"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#EAF0F6] text-sm font-semibold text-[#203C5A]"
        >
          {avatarLetter}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-slate-800">
            {name || email || "Account"}
          </span>
          {name && email && (
            <span className="block truncate text-xs text-slate-500" title={email}>
              {email}
            </span>
          )}
        </span>
        <UserRound size={16} className="shrink-0 text-slate-400" aria-hidden="true" />
      </button>
    </div>
  );
}
