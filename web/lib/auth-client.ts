export function authHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = window.localStorage.getItem("intellitutor_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function currentAuthUser(): { id?: number; username?: string; display_name?: string; is_admin?: boolean } | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem("intellitutor_user");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
