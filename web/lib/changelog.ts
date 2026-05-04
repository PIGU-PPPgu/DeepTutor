/**
 * IntelliTutor changelog — add new entries at the TOP.
 * The `id` must be unique and increasing (use YYYYMMDDNN format).
 * When a user dismisses the modal, their lastSeenId is saved to localStorage.
 */

export interface ChangelogEntry {
  id: number;
  date: string;        // YYYY-MM-DD
  title: string;
  items: string[];
}

export const CHANGELOG: ChangelogEntry[] = [
  {
    id: 2026050401,
    date: "2026-05-04",
    title: "🎉 IntelliTutor v1.3.6 升级",
    items: [
      "升级到 DeepTutor v1.3.6 基座，性能大幅提升",
      "新增 Book 模块 — AI 自动生成整本教材",
      "新增 Skills 自定义技能系统",
      "新增 Gemini embedding 支持",
      "新增 NVIDIA NIM 模型支持",
      "知识图谱、认证系统、管理后台保持不变",
    ],
  },
];

const STORAGE_KEY = "intellitutor_last_changelog_id";

export function getLastSeenId(): number {
  if (typeof window === "undefined") return 0;
  return Number(window.localStorage.getItem(STORAGE_KEY) || 0);
}

export function setLastSeenId(id: number): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, String(id));
}

export function getUnseenEntries(): ChangelogEntry[] {
  const lastId = getLastSeenId();
  return CHANGELOG.filter((e) => e.id > lastId);
}
