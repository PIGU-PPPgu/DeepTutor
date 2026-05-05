"use client";

import { useEffect, useState, useRef } from "react";
import { LogOut, User, ChevronDown } from "lucide-react";
import { currentAuthUser, authHeaders } from "@/lib/auth-client";

export function UserMenu({ collapsed = false }: { collapsed?: boolean }) {
  const [user, setUser] = useState<ReturnType<typeof currentAuthUser>>(null);
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setUser(currentAuthUser());
  }, []);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handleLogout = () => {
    localStorage.removeItem("intellitutor_token");
    localStorage.removeItem("intellitutor_user");
    window.location.href = "/";
  };

  if (!user) return null;

  const displayName = user.display_name || user.username || "User";
  const initial = displayName.charAt(0).toUpperCase();

  if (collapsed) {
    return (
      <div ref={menuRef} className="relative">
        <button
          onClick={() => setOpen(!open)}
          className="flex h-9 w-9 items-center justify-center rounded-xl text-[var(--muted-foreground)]/70 transition-colors hover:bg-[var(--background)]/50 hover:text-[var(--foreground)]"
          title={displayName}
        >
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--foreground)] text-[10px] font-bold text-[var(--background)]">
            {initial}
          </span>
        </button>

        {open && (
          <div className="absolute left-full bottom-0 ml-2 w-48 rounded-xl border border-[var(--border)] bg-[var(--background)] py-1 shadow-xl">
            <div className="border-b border-[var(--border)] px-3 py-2">
              <p className="text-sm font-medium text-[var(--foreground)]">{displayName}</p>
              <p className="text-xs text-[var(--muted-foreground)]">@{user.username}</p>
            </div>
            {user.is_admin && (
              <a
                href="/admin/users"
                className="flex items-center gap-2 px-3 py-2 text-sm text-[var(--foreground)] transition-colors hover:bg-[var(--secondary)]"
              >
                <User size={14} />
                <span>管理后台</span>
              </a>
            )}
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-500 transition-colors hover:bg-[var(--secondary)]"
            >
              <LogOut size={14} />
              <span>退出登录</span>
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div ref={menuRef} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--background)]/60"
      >
        {/* Avatar circle */}
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--foreground)] text-xs font-bold text-[var(--background)]">
          {initial}
        </span>
        <span className="max-w-[80px] truncate text-[var(--foreground)]">{displayName}</span>
        <ChevronDown size={14} className="text-[var(--muted-foreground)]" />
      </button>

      {open && (
        <div className="absolute right-0 bottom-full mb-1 w-48 rounded-xl border border-[var(--border)] bg-[var(--background)] py-1 shadow-xl">
          <div className="border-b border-[var(--border)] px-3 py-2">
            <p className="text-sm font-medium text-[var(--foreground)]">{displayName}</p>
            <p className="text-xs text-[var(--muted-foreground)]">@{user.username}</p>
          </div>
          {user.is_admin && (
            <a
              href="/admin/users"
              className="flex items-center gap-2 px-3 py-2 text-sm text-[var(--foreground)] transition-colors hover:bg-[var(--secondary)]"
            >
              <User size={14} />
              <span>管理后台</span>
            </a>
          )}
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-500 transition-colors hover:bg-[var(--secondary)]"
          >
            <LogOut size={14} />
            <span>退出登录</span>
          </button>
        </div>
      )}
    </div>
  );
}
