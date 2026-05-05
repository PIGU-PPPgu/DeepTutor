import UtilitySidebar from "@/components/sidebar/UtilitySidebar";
import { AuthGuard } from "@/components/AuthGuard";

export default function UtilityLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden">
        <UtilitySidebar />
        <main className="flex-1 overflow-hidden bg-[var(--background)]">
          {children}
        </main>
      </div>
    </AuthGuard>
  );
}
