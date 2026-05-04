"use client";

import { useEffect, useState } from "react";
import { X, Sparkles } from "lucide-react";
import { getUnseenEntries, setLastSeenId } from "@/lib/changelog";
import type { ChangelogEntry } from "@/lib/changelog";

export function ChangelogModal() {
  const [entries, setEntries] = useState<ChangelogEntry[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const unseen = getUnseenEntries();
    if (unseen.length > 0) {
      setEntries(unseen);
      setOpen(true);
    }
  }, []);

  if (!open || entries.length === 0) return null;

  const handleClose = () => {
    const maxId = Math.max(...entries.map((e) => e.id));
    setLastSeenId(maxId);
    setOpen(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="relative mx-4 w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--background)] p-6 shadow-2xl">
        <button
          onClick={handleClose}
          className="absolute right-4 top-4 rounded-md p-1 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--secondary)] hover:text-[var(--foreground)]"
        >
          <X size={18} />
        </button>

        <div className="mb-4 flex items-center gap-2">
          <Sparkles size={20} className="text-amber-500" />
          <h2 className="text-lg font-semibold text-[var(--foreground)]">更新公告</h2>
        </div>

        <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
          {entries.map((entry) => (
            <div key={entry.id} className="space-y-2">
              <div className="flex items-baseline gap-2">
                <span className="text-sm font-medium text-[var(--foreground)]">{entry.title}</span>
                <span className="text-xs text-[var(--muted-foreground)]">{entry.date}</span>
              </div>
              <ul className="space-y-1 pl-1">
                {entry.items.map((item, i) => (
                  <li
                    key={i}
                    className="text-sm leading-relaxed text-[var(--foreground)]/80 before:mr-2 before:text-[var(--muted-foreground)] before:content-['•']"
                  >
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <button
          onClick={handleClose}
          className="mt-5 w-full rounded-xl bg-[var(--foreground)] px-4 py-2.5 text-sm font-medium text-[var(--background)] transition-opacity hover:opacity-90"
        >
          知道了
        </button>
      </div>
    </div>
  );
}
