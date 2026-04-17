/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { useState } from "react";
import { GitMerge, RefreshCw, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";

type SyncState = "idle" | "checking" | "syncing" | "success" | "error";

export default function GitSyncButton() {
  const [state, setState] = useState<SyncState>("idle");
  const [message, setMessage] = useState("");
  const [currentCommit, setCurrentCommit] = useState("");
  const [upstreamCommit, setUpstreamCommit] = useState("");

  const checkStatus = async () => {
    setState("checking");
    try {
      const res = await fetch(apiUrl("/api/v1/system/git-status"));
      const data = await res.json();
      setCurrentCommit(data.current_commit);
      setUpstreamCommit(data.upstream_commit);
      setMessage(data.message);
      setState(data.success ? "idle" : "error");
    } catch {
      setMessage("无法连接服务器");
      setState("error");
    }
  };

  const doSync = async () => {
    setState("syncing");
    try {
      const res = await fetch(apiUrl("/api/v1/system/git-sync"), { method: "POST" });
      const data = await res.json();
      setMessage(data.message);
      setCurrentCommit(data.current_commit);
      setUpstreamCommit(data.upstream_commit);
      setState(data.success ? "success" : "error");
    } catch {
      setMessage("同步请求失败");
      setState("error");
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-6 space-y-4">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-500/10">
          <GitMerge className="h-5 w-5 text-purple-500" />
        </div>
        <div>
          <h3 className="text-sm font-semibold">一键同步主仓库</h3>
          <p className="text-xs text-muted-foreground">
            与 DeepTutor 上游仓库保持同步，获取最新功能
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={checkStatus}
          disabled={state === "checking" || state === "syncing"}
          className="flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm hover:bg-accent transition disabled:opacity-50"
        >
          {state === "checking" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          检查更新
        </button>

        <button
          onClick={doSync}
          disabled={state === "syncing" || state === "checking"}
          className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm text-white hover:bg-purple-700 transition disabled:opacity-50"
        >
          {state === "syncing" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <GitMerge className="h-4 w-4" />
          )}
          一键同步
        </button>
      </div>

      {message && (
        <div
          className={`flex items-center gap-2 rounded-lg p-3 text-sm ${
            state === "success"
              ? "bg-green-500/10 text-green-600"
              : state === "error"
                ? "bg-red-500/10 text-red-600"
                : "bg-muted text-muted-foreground"
          }`}
        >
          {state === "success" ? (
            <CheckCircle2 className="h-4 w-4 shrink-0" />
          ) : state === "error" ? (
            <AlertCircle className="h-4 w-4 shrink-0" />
          ) : null}
          {message}
          {currentCommit && (
            <span className="ml-auto text-xs opacity-60">
              {currentCommit}
              {upstreamCommit && upstreamCommit !== currentCommit && ` → ${upstreamCommit}`}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
