"use client";

import { useEffect, useState, type ReactNode } from "react";
import { currentAuthUser } from "@/lib/auth-client";

/**
 * AuthGuard: redirects to /login if no authenticated user found.
 * Wrap page content with this component.
 */
export function AuthGuard({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    const user = currentAuthUser();
    if (user) {
      setAuthed(true);
      setReady(true);
    } else {
      // Not logged in, redirect to login
      window.location.href = "/login";
    }
  }, []);

  if (!ready) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--background)]">
        <div className="text-[var(--muted-foreground)] text-sm">Loading...</div>
      </div>
    );
  }

  if (!authed) return null;
  return <>{children}</>;
}
