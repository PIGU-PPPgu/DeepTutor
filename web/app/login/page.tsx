"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";

export default function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { login, register } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "login") {
        await login(username, password);
      } else {
        await register(username, password, displayName || username, inviteCode);
      }
      router.push("/");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--background)]">
      <div className="w-full max-w-sm p-8 rounded-2xl border border-[var(--border)] bg-[var(--card)] shadow-lg">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-[var(--foreground)]">IntelliTutor</h1>
          <p className="text-sm text-[var(--muted)] mt-1">
            {mode === "login" ? "登录你的账号" : "创建新账号"}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-[var(--foreground)] mb-1">用户名</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="输入用户名"
              required
              autoFocus
            />
          </div>

          {mode === "register" && (
            <div>
              <label className="block text-sm font-medium text-[var(--foreground)] mb-1">昵称</label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="你的名字（可选）"
              />
            </div>
          )}

          {mode === "register" && (
            <div>
              <label className="block text-sm font-medium text-[var(--foreground)] mb-1">邀请码</label>
              <input
                type="text"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value.trim())}
                className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="输入邀请注册码"
                required
              />
              <p className="mt-1 text-xs text-[var(--muted)]">注册暂时仅开放给受邀用户。</p>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-[var(--foreground)] mb-1">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="输入密码"
              required
            />
          </div>

          {error && (
            <div className="text-red-500 text-sm text-center">{error}</div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium transition disabled:opacity-50"
          >
            {busy ? "请稍候..." : mode === "login" ? "登录" : "注册"}
          </button>
        </form>

        <div className="mt-6 text-center text-sm text-[var(--muted)]">
          {mode === "login" ? (
            <>
              还没有账号？{" "}
              <button
                onClick={() => { setMode("register"); setError(""); }}
                className="text-blue-500 hover:underline"
              >
                注册
              </button>
            </>
          ) : (
            <>
              已有账号？{" "}
              <button
                onClick={() => { setMode("login"); setError(""); }}
                className="text-blue-500 hover:underline"
              >
                登录
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
