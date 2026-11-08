import { useState } from "react";
import { Check, Download, Loader2, Save } from "lucide-react";
import { useAuth } from "../context/useAuth.js";
import { usePageTitle } from "../hooks/usePageTitle.js";
import { useInstallPrompt } from "../hooks/useInstallPrompt.js";

export default function SettingsPage() {
  usePageTitle("Account Settings");
  const { user, updateUser } = useAuth();
  const [fullName, setFullName] = useState(
    () => user?.user_metadata?.full_name || user?.user_metadata?.name || "",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const { canInstall, isInstalled, promptInstall } = useInstallPrompt();
  const [installStatus, setInstallStatus] = useState("");

  const savedName = user?.user_metadata?.full_name || user?.user_metadata?.name || "";

  async function handleInstallClick() {
    const outcome = await promptInstall();
    if (outcome === "dismissed") setInstallStatus("No problem — you can install Waymark any time from here.");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const { error: updateError } = await updateUser({
        data: { ...user.user_metadata, full_name: fullName.trim() },
      });
      if (updateError) throw updateError;
      setSuccess("Your profile has been updated.");
    } catch (updateError) {
      setError(updateError.message || "Unable to update your profile. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl p-5 sm:p-8">
      <div className="mb-6">
        <p className="text-sm font-medium text-[#52708D]">ACCOUNT</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-2 text-sm text-slate-500">Manage the name shown on your Waymark profile.</p>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
        <form onSubmit={handleSubmit} className="max-w-lg space-y-5">
          <div>
            <label htmlFor="account-email" className="mb-2 block text-sm font-medium">Email address</label>
            <input
              id="account-email"
              type="email"
              value={user?.email || ""}
              readOnly
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500"
            />
            <p className="mt-2 text-xs text-slate-500">Your email is managed by your sign-in provider.</p>
          </div>

          <div>
            <label htmlFor="account-name" className="mb-2 block text-sm font-medium">Display name</label>
            <input
              id="account-name"
              type="text"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              autoComplete="name"
              maxLength={80}
              required
              disabled={saving}
              className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-[#203C5A] focus:ring-2 focus:ring-[#EAF0F6] disabled:bg-slate-50"
            />
          </div>

          {error && <p className="text-sm text-red-700" role="alert">{error}</p>}
          {success && (
            <p className="flex items-center gap-2 text-sm text-emerald-700" role="status">
              <Check size={16} />
              {success}
            </p>
          )}

          <button
            type="submit"
            disabled={saving || fullName.trim() === savedName}
            className="inline-flex items-center gap-2 rounded-xl bg-[#203C5A] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[#172E46] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            {saving ? "Saving…" : "Save changes"}
          </button>
        </form>
      </section>

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
        <h2 className="text-base font-semibold">App</h2>
        <p className="mt-1 text-sm text-slate-500">
          Install Waymark on this device for one-tap access and offline-friendly maps.
        </p>
        <div className="mt-4">
          {isInstalled ? (
            <p className="flex items-center gap-2 text-sm text-emerald-700">
              <Check size={16} />
              Waymark is installed on this device.
            </p>
          ) : canInstall ? (
            <button
              type="button"
              onClick={handleInstallClick}
              className="inline-flex items-center gap-2 rounded-xl bg-[#203C5A] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[#172E46]"
            >
              <Download size={16} />
              Install Waymark
            </button>
          ) : (
            <p className="text-sm text-slate-500">
              One-tap install isn&apos;t available in this browser — look for
              &quot;Add to Home Screen&quot; or &quot;Install app&quot; in your browser&apos;s menu instead.
            </p>
          )}
          {installStatus && (
            <p className="mt-2 text-sm text-slate-500" role="status">{installStatus}</p>
          )}
        </div>
      </section>
    </main>
  );
}
