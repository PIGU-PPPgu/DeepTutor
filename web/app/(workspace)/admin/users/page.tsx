"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
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

function tokenHeaders() {
  const token = localStorage.getItem("intellitutor_token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export default function AdminUsersPage() {
  const { user, loading: authLoading } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [invite, setInvite] = useState<InviteInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const isAdmin = !!user?.is_admin;

  const loadUsers = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(apiUrl("/api/admin/users"), { headers: tokenHeaders() });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setUsers(data.users || []);
      setInvite(data.invite || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载用户失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin) void loadUsers();
  }, [isAdmin]);

  const stats = useMemo(() => {
    return {
      total: users.length,
      active: users.filter((u) => !u.is_disabled).length,
      admins: users.filter((u) => u.is_admin).length,
      disabled: users.filter((u) => u.is_disabled).length,
    };
  }, [users]);

  const updateUser = async (id: number, patch: Partial<Pick<AdminUser, "is_admin" | "is_disabled" | "display_name">>) => {
    setMessage("");
    setError("");
    const res = await fetch(apiUrl(`/api/admin/users/${id}`), {
      method: "PATCH",
      headers: tokenHeaders(),
      body: JSON.stringify(patch),
    });
    if (!res.ok) {
      setError(await res.text());
      return;
    }
    setMessage("已更新");
    await loadUsers();
  };

  const resetPassword = async (id: number, username: string) => {
    const password = prompt(`给 ${username} 设置新密码：`);
    if (!password) return;
    if (password.length < 4) {
      setError("密码至少 4 位。建议别用弱密码，真的别。");
      return;
    }
    setMessage("");
    setError("");
    const res = await fetch(apiUrl(`/api/admin/users/${id}/reset-password`), {
      method: "POST",
      headers: tokenHeaders(),
      body: JSON.stringify({ password }),
    });
    if (!res.ok) {
      setError(await res.text());
      return;
    }
    setMessage(`已重置 ${username} 的密码`);
  };

  if (authLoading) {
    return <div className="p-6 text-sm text-[var(--muted-foreground)]">正在检查权限…</div>;
  }

  if (!user) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-semibold text-[var(--foreground)]">用户管理</h1>
        <p className="mt-3 text-sm text-[var(--muted-foreground)]">请先登录管理员账号。</p>
        <Link href="/login" className="mt-4 inline-flex rounded-lg bg-[var(--foreground)] px-3 py-2 text-sm text-[var(--background)]">去登录</Link>
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-semibold text-[var(--foreground)]">用户管理</h1>
        <p className="mt-3 text-sm text-[var(--muted-foreground)]">当前账号没有管理员权限。</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6 text-[var(--foreground)]">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">用户管理</h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">管理注册用户、禁用账号、重置密码和管理员权限。</p>
        </div>
        <button
          onClick={() => loadUsers()}
          className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm hover:bg-[var(--secondary)]"
        >
          {loading ? "刷新中…" : "刷新"}
        </button>
      </div>

      <div className="mb-6 grid gap-3 md:grid-cols-5">
        {[['总用户', stats.total], ['可用', stats.active], ['管理员', stats.admins], ['已禁用', stats.disabled]].map(([label, value]) => (
          <div key={String(label)} className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
            <div className="text-xs text-[var(--muted-foreground)]">{label}</div>
            <div className="mt-1 text-2xl font-semibold">{value}</div>
          </div>
        ))}
        <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
          <div className="text-xs text-[var(--muted-foreground)]">邀请码</div>
          <div className="mt-1 text-sm font-medium">{invite?.enabled ? invite.code : "未启用"}</div>
          {invite?.enabled && <div className="mt-1 text-xs text-[var(--muted-foreground)]">{invite.used}/{invite.limit || "∞"}</div>}
        </div>
      </div>

      {message && <div className="mb-3 rounded-lg border border-green-500/30 bg-green-500/10 px-3 py-2 text-sm text-green-600">{message}</div>}
      {error && <div className="mb-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600">{error}</div>}

      <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--card)]">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-[var(--border)] bg-[var(--secondary)] text-xs text-[var(--muted-foreground)]">
            <tr>
              <th className="px-4 py-3">用户</th>
              <th className="px-4 py-3">角色</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3">注册时间</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-[var(--border)] last:border-b-0">
                <td className="px-4 py-3">
                  <div className="font-medium">{u.display_name || u.username}</div>
                  <div className="text-xs text-[var(--muted-foreground)]">@{u.username}</div>
                </td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => updateUser(u.id, { is_admin: !u.is_admin })}
                    className={`rounded-full px-2 py-1 text-xs ${u.is_admin ? "bg-blue-500/15 text-blue-600" : "bg-[var(--secondary)] text-[var(--muted-foreground)]"}`}
                  >
                    {u.is_admin ? "管理员" : "普通用户"}
                  </button>
                </td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-1 text-xs ${u.is_disabled ? "bg-red-500/15 text-red-600" : "bg-green-500/15 text-green-600"}`}>
                    {u.is_disabled ? "已禁用" : "正常"}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-[var(--muted-foreground)]">{new Date(u.created_at).toLocaleString()}</td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <button onClick={() => resetPassword(u.id, u.username)} className="rounded-md border border-[var(--border)] px-2 py-1 text-xs hover:bg-[var(--secondary)]">重置密码</button>
                    <button
                      onClick={() => updateUser(u.id, { is_disabled: !u.is_disabled })}
                      className="rounded-md border border-[var(--border)] px-2 py-1 text-xs hover:bg-[var(--secondary)]"
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
    </div>
  );
}
