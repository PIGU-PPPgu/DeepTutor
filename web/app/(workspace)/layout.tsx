"use client";

import WorkspaceSidebar from "@/components/sidebar/WorkspaceSidebar";
import { UnifiedChatProvider } from "@/context/UnifiedChatContext";
import { useAuth } from "@/components/AuthProvider";

function UserMenu() {
  const { user, logout } = useAuth();
  if (!user) return null;
  return (
    <div className="absolute top-3 right-4 flex items-center gap-2 text-sm text-[var(--muted)] z-50">
      <span>{user.display_name || user.username}</span>
      <button
        onClick={() => logout()}
        className="px-2 py-1 rounded-md hover:bg-[var(--border)] text-xs"
      >
        退出
      </button>
    </div>
  );
}

export default function WorkspaceLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <UnifiedChatProvider>
      <div className="flex h-screen overflow-hidden relative">
        <UserMenu />
        <WorkspaceSidebar />
        <main className="flex-1 overflow-hidden bg-[var(--background)]">{children}</main>
      </div>
    </UnifiedChatProvider>
  );
}
