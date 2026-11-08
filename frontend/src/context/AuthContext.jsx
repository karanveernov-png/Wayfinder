import { useEffect, useState } from "react";
import { AuthContext } from "./AuthContextValue.js";
import { supabase } from "../lib/supabase.js";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setLoading(false);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, session) => {
      setUser(session?.user ?? null);
    });
    return () => subscription.unsubscribe();
  }, []);

  const signIn = (email, password) => supabase.auth.signInWithPassword({ email, password });
  const signUp = (email, password, fullName) =>
    supabase.auth.signUp({
      email,
      password,
      options: { data: { full_name: fullName } },
    });
  const updateUser = (attributes) => supabase.auth.updateUser(attributes);
  const signOut = () => supabase.auth.signOut();

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signUp, updateUser, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}