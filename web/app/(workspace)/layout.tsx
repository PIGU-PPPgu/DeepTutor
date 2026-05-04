import WorkspaceSidebar from "@/components/sidebar/WorkspaceSidebar";
import { UnifiedChatProvider } from "@/context/UnifiedChatContext";
import { ChangelogModal } from "@/components/ChangelogModal";

export default function WorkspaceLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <UnifiedChatProvider>
      <ChangelogModal />
      <div className="flex h-screen overflow-hidden">
        <WorkspaceSidebar />
        <main className="flex-1 overflow-hidden bg-[var(--background)]">
          {children}
        </main>
      </div>
    </UnifiedChatProvider>
  );
}
