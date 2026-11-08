import { useState } from "react";
import { Mail, Lock, UserPlus, LogIn, UserRound } from "lucide-react";
import { useAuth } from "../context/useAuth.js";
import { useNavigate, useLocation } from "react-router-dom";
import { usePageTitle } from "../hooks/usePageTitle.js";

export default function LoginPage() {
  const [isSignUp, setIsSignUp] = useState(false);
  usePageTitle(isSignUp ? "Sign Up" : "Sign In");
  const { signIn, signUp, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setNotice("");
    setIsSubmitting(true);
    try {
      const result = isSignUp
        ? await signUp(email.trim(), password, fullName.trim())
        : await signIn(email.trim(), password);
      if (result.error) throw result.error;
      if (isSignUp && !result.data.session) {
        setNotice("Account created. Check your email for a confirmation link before signing in.");
        return;
      }
      navigate(location.state?.from?.pathname || "/trip-planner", { replace: true });
    } catch (e) {
      setError(e.message || "Unable to complete your request. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  const isBusy = loading || isSubmitting;

  return (
    <main className="min-h-screen bg-[#F7F8FA] p-5">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between py-2">
        <div className="text-lg font-bold text-[#203C5A]">waymark</div>
        <button
          type="button"
          onClick={() => {
            setIsSignUp(!isSignUp);
            setError("");
            setNotice("");
          }}
          disabled={isBusy}
          className="inline-flex items-center gap-2 rounded-xl bg-[#203C5A] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#172E46]"
        >
          {isSignUp ? <LogIn size={16} /> : <UserPlus size={16} />}
          {isSignUp ? "Sign in" : "Sign up"}
        </button>
      </header>

      <div className="flex min-h-[calc(100vh-76px)] items-center justify-center">
        <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8">
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-semibold">{isSignUp ? "Create account" : "Sign in"}</h1>
            <p className="mt-1 text-sm text-slate-500">
              {isSignUp ? "Start saving your journeys" : "Access your saved trips"}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {isSignUp && (
              <div>
                <label className="mb-1 block text-sm font-medium" htmlFor="full-name">Name</label>
                <div className="relative">
                  <UserRound className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                  <input
                    id="full-name"
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 py-3 pl-10 pr-4 outline-none focus:border-[#203C5A]"
                    placeholder="Your name"
                    autoComplete="name"
                    required
                    maxLength={80}
                    disabled={isBusy}
                  />
                </div>
              </div>
            )}
            <div>
              <label className="mb-1 block text-sm font-medium">Email</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 py-3 pl-10 pr-4 outline-none focus:border-[#203C5A]"
                  placeholder="you@example.com"
                  required
                  disabled={isBusy}
                />
              </div>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 py-3 pl-10 pr-4 outline-none focus:border-[#203C5A]"
                  placeholder="••••••••"
                  required
                  minLength={6}
                  disabled={isBusy}
                />
              </div>
            </div>

            {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
            {notice && <p className="text-sm text-emerald-700" role="status">{notice}</p>}

            <button
              type="submit"
              disabled={isBusy}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#203C5A] px-5 py-3 font-medium text-white hover:bg-[#172E46] disabled:opacity-60"
            >
              {isBusy ? "Please wait…" : isSignUp ? <><UserPlus size={16} /> Create account</> : <><LogIn size={16} /> Sign in</>}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-500">
            {isSignUp ? "Already have an account?" : "Need an account?"}{" "}
            <button
              type="button"
              onClick={() => {
                setIsSignUp(!isSignUp);
                setError("");
                setNotice("");
              }}
              disabled={isBusy}
              className="font-medium text-[#203C5A] hover:underline"
            >
              {isSignUp ? "Sign in" : "Sign up"}
            </button>
          </p>
        </div>
      </div>
    </main>
  );
}