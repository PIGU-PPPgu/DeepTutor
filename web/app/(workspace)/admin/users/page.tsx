"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { apiUrl } from "@/lib/api";

type AdminUser = {
  id: number;
  username: string;
  display_name: string;
  invite_code: string | null;
  is_admin: boolean;
  is_disabled: boolean;
  created_at: string;
};

type InviteInfo = {
  enabled: boolean;
  code: string | null;
  limit: number;
  used: number;
};

type CurrentUser = {
  id: number;
  username: string;
  display_name: string;
  is_admin?: boolean;
};

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("intellitutor_token");
}

function getCurrentUser(): CurrentUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("intellitutor_user");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as CurrentUser;
  } catch {
    return null;
  }
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function StatCard({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 flex flex-col gap-1">
      <span className="text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wider">{label}</span>
      <span className={`text-2xl font-bold tabular-nums ${accent ?? "text-[var(--foreground)]"}`}>{value}</span>
    </div>
  );
}

function Badge({ children, variant }: { children: React.ReactNode; variant: "admin" | "user" | "active" | "disabled" }) {
  const styles = {
    admin: "bg-blue-500/12 text-blue-600 border border-blue-500/20",
    user: "bg-[var(--secondary)] text-[var(--muted-foreground)] border border-[var(--border)]",
    active: "bg-emerald-500/12 text-emerald-600 border border-emerald-500/20",
    disabled: "bg-red-500/12 text-red-600 border border-red-500/20",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[variant]}`}>
      {children}
    </span>
  );
}

export default function AdminUsersPage() {
  const router = useRouter();
  const [authReady, setAuthReady] = useState(false);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [invite, setInvite] = useState<InviteInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");

  // Auth guard: read from localStorage, redirect if not admin
  useEffect(() => {
    const user = getCurrentUser();
    const token = getToken();
    if (!token || !user) {
      router.replace("/chat");
      return;
    }
    if (!user.is_admin) {
      router.replace("/chat");
      return;
    }
    setCurrentUser(user);
    setAuthReady(true);
  }, [router]);

  const loadUsers = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(apiUrl("/api/admin/users"), { headers: authHeaders() });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Error ${res.status}`);
      }
      const data = await res.json();
      setUsers(data.users ?? []);
      setInvite(data.invite ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载用户列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (authReady) void loadUsers();
  }, [authReady]);

  const stats = useMemo(() => ({
    total: users.length,
    active: users.filter((u) => !u.is_disabled).length,
    admins: users.filter((u) => u.is_admin).length,
    disabled: users.filter((u) => u.is_disabled).length,
  }), [users]);

  const flash = (msg: string, isError = false) => {
    if (isError) { setError(msg); setMessage(""); }
    else { setMessage(msg); setError(""); }
    setTimeout(() => { setMessage(""); setError(""); }, 4000);
  };

  const updateUser = async (id: number, patch: Partial<Pick<AdminUser, "is_admin" | "is_disabled" | "display_name">>) => {
    try {
      const res = await fetch(apiUrl(`/api/admin/users/${id}`), {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify(patch),
      });
      if (!res.ok) throw new Error(await res.text());
      flash("已更新");
      await loadUsers();
    } catch (e) {
      flash(e instanceof Error ? e.message : "更新失败", true);
    }
  };

  const saveDisplayName = async (id: number) => {
    const name = editName.trim();
    if (!name) return;
    await updateUser(id, { display_name: name });
    setEditingId(null);
  };

  const resetPassword = async (id: number, username: string) => {
    const password = prompt(`为 @${username} 设置新密码：`);
    if (!password) return;
    if (password.length < 4) {
      flash("密码至少需要 4 位", true);
      return;
    }
    try {
      const res = await fetch(apiUrl(`/api/admin/users/${id}/reset-password`), {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ password }),
      });
      if (!res.ok) throw new Error(await res.text());
      flash(`已重置 @${username} 的密码`);
    } catch (e) {
      flash(e instanceof Error ? e.message : "重置密码失败", true);
    }
  };

  if (!authReady) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-[var(--muted-foreground)]">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--foreground)]" />
          <span className="text-sm">验证权限中…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-6 py-8">
        {/* Header */}
        <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-[var(--foreground)]">用户管理</h1>
            <p className="mt-1 text-sm text-[var(--muted-foreground)]">
              管理所有注册用户 · 当前登录：<span className="font-medium text-[var(--foreground)]">{currentUser?.display_name || currentUser?.username}</span>
            </p>
          </div>
          <button
            onClick={() => void loadUsers()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--card)] px-4 py-2 text-sm font-medium text-[var(--foreground)] hover:bg-[var(--secondary)] disabled:opacity-50 transition-colors"
          >
            {loading ? (
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--foreground)]" />
            ) : (
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            )}
            {loading ? "刷新中" : "刷新"}
          </button>
        </div>

        {/* Stats */}
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-5">
          <StatCard label="总用户" value={stats.total} />
          <StatCard label="正常" value={stats.active} accent="text-emerald-600" />
          <StatCard label="管理员" value={stats.admins} accent="text-blue-600" />
          <StatCard label="已禁用" value={stats.disabled} accent="text-red-600" />
          <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 flex flex-col gap-1">
            <span className="text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wider">邀请码</span>
            {invite?.enabled ? (
              <>
                <span className="text-sm font-mono font-semibold text-[var(--foreground)] truncate">{invite.code}</span>
                <span className="text-xs text-[var(--muted-foreground)]">已用 {invite.used} / {invite.limit || "∞"}</span>
              </>
            ) : (
              <span className="text-sm text-[var(--muted-foreground)]">未启用</span>
            )}
          </div>
        </div>

        {/* Feedback */}
        {message && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/8 px-4 py-2.5 text-sm text-emerald-700">
            <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            {message}
          </div>
        )}
        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/8 px-4 py-2.5 text-sm text-red-700">
            <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {error}
          </div>
        )}

        {/* Table */}
        <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--card)] shadow-sm">
          {loading && users.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-20 text-[var(--muted-foreground)]">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--foreground)]" />
              <span className="text-sm">加载用户列表…</span>
            </div>
          ) : users.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-20 text-[var(--muted-foreground)]">
              <svg className="h-10 w-10 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
              </svg>
              <span className="text-sm">暂无用户</span>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-[var(--border)] bg-[var(--secondary)]">
                  <tr>
                    <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">用户</th>
                    <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">角色</th>
                    <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">状态</th>
                    <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">注册时间</th>
                    <th className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {users.map((u) => (
                    <tr key={u.id} className={`transition-colors hover:bg-[var(--secondary)]/40 ${u.is_disabled ? "opacity-60" : ""}`}>
                      {/* User */}
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-3">
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--secondary)] text-xs font-semibold text-[var(--foreground)] uppercase">
                            {(u.display_name || u.username).charAt(0)}
                          </div>
                          <div>
                            {editingId === u.id ? (
                              <div className="flex items-center gap-1.5">
                                <input
                                  autoFocus
                                  className="w-32 rounded border border-[var(--border)] bg-[var(--background)] px-2 py-0.5 text-sm text-[var(--foreground)] outline-none focus:border-[var(--foreground)]"
                                  value={editName}
                                  onChange={(e) => setEditName(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") void saveDisplayName(u.id);
                                    if (e.key === "Escape") setEditingId(null);
                                  }}
                                />
                                <button onClick={() => void saveDisplayName(u.id)} className="text-xs text-emerald-600 hover:underline">保存</button>
                                <button onClick={() => setEditingId(null)} className="text-xs text-[var(--muted-foreground)] hover:underline">取消</button>
                              </div>
                            ) : (
                              <button
                                className="font-medium text-[var(--foreground)] hover:underline text-left"
                                onClick={() => { setEditingId(u.id); setEditName(u.display_name || u.username); }}
                                title="点击编辑显示名"
                              >
                                {u.display_name || u.username}
                              </button>
                            )}
                            <div className="text-xs text-[var(--muted-foreground)]">@{u.username}</div>
                          </div>
                        </div>
                      </td>

                      {/* Role */}
                      <td className="px-5 py-3.5">
                        <button
                          onClick={() => void updateUser(u.id, { is_admin: !u.is_admin })}
                          title={u.is_admin ? "点击撤销管理员" : "点击设为管理员"}
                          className="cursor-pointer transition-opacity hover:opacity-75"
                        >
                          <Badge variant={u.is_admin ? "admin" : "user"}>
                            {u.is_admin ? "管理员" : "普通用户"}
                          </Badge>
                        </button>
                      </td>

                      {/* Status */}
                      <td className="px-5 py-3.5">
                        <Badge variant={u.is_disabled ? "disabled" : "active"}>
                          {u.is_disabled ? "已禁用" : "正常"}
                        </Badge>
                      </td>

                      {/* Created */}
                      <td className="px-5 py-3.5 text-xs text-[var(--muted-foreground)]">
                        {new Date(u.created_at).toLocaleString("zh-CN", { dateStyle: "short", timeStyle: "short" })}
                      </td>

                      {/* Actions */}
                      <td className="px-5 py-3.5">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => void resetPassword(u.id, u.username)}
                            className="rounded-md border border-[var(--border)] bg-[var(--background)] px-2.5 py-1 text-xs font-medium text-[var(--foreground)] hover:bg-[var(--secondary)] transition-colors"
                          >
                            重置密码
                          </button>
                          <button
                            onClick={() => void updateUser(u.id, { is_disabled: !u.is_disabled })}
                            className={`rounded-md border px-2.5 py-1 text-xs font-medium transition-colors ${
                              u.is_disabled
                                ? "border-emerald-500/30 bg-emerald-500/8 text-emerald-700 hover:bg-emerald-500/15"
                                : "border-red-500/30 bg-red-500/8 text-red-700 hover:bg-red-500/15"
                            }`}
                          >
                            {u.is_disabled ? "启用" : "禁用"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <p className="mt-4 text-xs text-[var(--muted-foreground)]">
          共 {stats.total} 名用户 · 点击角色徽章可切换管理员权限 · 点击显示名可重命名
        </p>
      </div>
    </div>
  );
}
