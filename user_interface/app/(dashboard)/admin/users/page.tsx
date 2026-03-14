"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useChatStore } from "@/store/chatStore";
import { apiFetch } from "@/lib/api";
import { ALL_ROLES } from "@/lib/constants";
import { ActiveUser, PendingUser, UserRole } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface ApproveResult {
  /** Relative path e.g. `/activate?token=<uuid>` */
  activation_link: string;
  activation_token: string;
}

/**
 * Admin-only page for managing judicial staff accounts.
 *
 * Two tabs:
 * - **Pending Requests** — approve / assign role for new registrations.
 *   On approval the backend emails the activation link; a copy-able
 *   fallback URL is shown in-page for out-of-band sharing.
 * - **Active Users** — suspend active users or reactivate suspended ones.
 *
 * Renders an access-denied message for non-admin users rather than
 * redirecting, to avoid a flash on initial render before the store hydrates.
 */
export default function AdminUsersPage() {
  const user = useChatStore((s) => s.user);

  // ── Tab ────────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<"pending" | "active">("pending");

  // ── Pending tab state ──────────────────────────────────────────────────
  const [pending, setPending] = useState<PendingUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState("");
  const [approving, setApproving] = useState<string | null>(null);
  const [approveErrors, setApproveErrors] = useState<Record<string, string>>({});
  const [roleOverrides, setRoleOverrides] = useState<Record<string, UserRole>>({});
  const [results, setResults] = useState<Record<string, ApproveResult>>({});
  const [copied, setCopied] = useState<string | null>(null);
  // Stable origin string — derived client-side to avoid SSR mismatch.
  const [origin, setOrigin] = useState("");
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Active users tab state ─────────────────────────────────────────────
  const [activeUsers, setActiveUsers] = useState<ActiveUser[]>([]);
  const [activeLoading, setActiveLoading] = useState(true);
  const [activeError, setActiveError] = useState("");
  const [suspending, setSuspending] = useState<string | null>(null);
  const [suspendErrors, setSuspendErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    setOrigin(window.location.origin);
    return () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  const fetchPending = useCallback(async () => {
    setLoading(true);
    setFetchError("");
    try {
      const data = await apiFetch<PendingUser[]>("/api/v1/auth/pending");
      setPending(data);
    } catch (err) {
      setFetchError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchActiveUsers = useCallback(async () => {
    setActiveLoading(true);
    setActiveError("");
    try {
      // Fetch active + suspended users so admins can reactivate suspended ones
      const [active, suspended] = await Promise.all([
        apiFetch<ActiveUser[]>("/api/v1/auth/users?status=active"),
        apiFetch<ActiveUser[]>("/api/v1/auth/users?status=suspended"),
      ]);
      setActiveUsers([...active, ...suspended]);
    } catch (err) {
      setActiveError((err as Error).message);
    } finally {
      setActiveLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user?.role === "admin") {
      fetchPending();
      fetchActiveUsers();
    }
  }, [user?.role, fetchPending, fetchActiveUsers]);

  if (user?.role !== "admin") {
    return (
      <div className="p-8 text-center text-gray-500">
        Access restricted to administrators.
      </div>
    );
  }

  async function handleApprove(userId: string, requestedRole: UserRole) {
    const role = roleOverrides[userId] ?? requestedRole;
    setApproving(userId);
    setApproveErrors((e) => ({ ...e, [userId]: "" }));
    try {
      const data = await apiFetch<ApproveResult>(`/api/v1/auth/approve/${userId}`, {
        method: "POST",
        body: JSON.stringify({ role }),
      });
      setResults((r) => ({ ...r, [userId]: data }));
      setPending((p) => p.filter((u) => u.id !== userId));
    } catch (err) {
      setApproveErrors((e) => ({ ...e, [userId]: (err as Error).message }));
    } finally {
      setApproving(null);
    }
  }

  async function handleUpdateStatus(userId: string, newStatus: "active" | "suspended") {
    setSuspending(userId);
    setSuspendErrors((e) => ({ ...e, [userId]: "" }));
    try {
      await apiFetch(`/api/v1/auth/users/${userId}/status`, {
        method: "POST",
        body: JSON.stringify({ status: newStatus }),
      });
      await fetchActiveUsers();
    } catch (err) {
      setSuspendErrors((e) => ({ ...e, [userId]: (err as Error).message }));
    } finally {
      setSuspending(null);
    }
  }

  function copyLink(userId: string, link: string) {
    navigator.clipboard.writeText(`${origin}${link}`).then(() => {
      setCopied(userId);
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setCopied(null), 2000);
    });
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">User Management</h1>
        <p className="text-gray-500 mt-1 text-sm">
          Review registration requests and manage judicial staff accounts
        </p>
      </div>

      {/* Tab bar */}
      <div className="mb-6 flex border-b border-gray-200">
        <button
          onClick={() => setActiveTab("pending")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "pending"
              ? "border-[#1a3a6b] text-[#1a3a6b]"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          Pending Requests
          {pending.length > 0 && (
            <span className="ml-2 bg-amber-100 text-amber-800 text-xs px-1.5 py-0.5 rounded-full">
              {pending.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab("active")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "active"
              ? "border-[#1a3a6b] text-[#1a3a6b]"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          Active Users
        </button>
      </div>

      {/* ── Pending tab ───────────────────────────────────────────────────── */}
      {activeTab === "pending" && (
        <>
          {/* Activation links generated this session */}
          {Object.keys(results).length > 0 && (
            <div className="mb-6 space-y-2">
              <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
                Approved — Activation link also sent by email
              </h2>
              {Object.entries(results).map(([uid, result]) => (
                <div
                  key={uid}
                  className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-lg px-4 py-3"
                >
                  <span className="text-sm text-green-800 flex-1 truncate font-mono">
                    {origin}{result.activation_link}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => copyLink(uid, result.activation_link)}
                    className="shrink-0"
                  >
                    {copied === uid ? "Copied!" : "Copy Link"}
                  </Button>
                </div>
              ))}
            </div>
          )}

          {loading ? (
            <div className="text-center py-12 text-gray-400">Loading requests…</div>
          ) : fetchError ? (
            <div className="text-center py-12 text-destructive">
              <p className="font-medium">Failed to load requests</p>
              <p className="text-sm mt-1">{fetchError}</p>
              <Button variant="outline" className="mt-4" onClick={fetchPending}>
                Retry
              </Button>
            </div>
          ) : pending.length === 0 ? (
            <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-xl">
              <p className="text-gray-400 font-medium">No pending requests</p>
              <p className="text-gray-300 text-sm mt-1">
                All registration requests have been reviewed
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {pending.map((u) => (
                <div key={u.id} className="bg-white border border-gray-200 rounded-xl p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-gray-900">{u.full_name}</span>
                        <Badge variant="outline" className="text-xs">
                          @{u.username}
                        </Badge>
                        {u.staff_number && (
                          <span className="text-xs text-gray-400">#{u.staff_number}</span>
                        )}
                      </div>
                      <div className="mt-1 text-sm text-gray-500 space-y-0.5">
                        <div>{u.email}</div>
                        <div>{u.court_station}</div>
                      </div>
                      <div className="mt-2 text-xs text-gray-400">
                        Requested:{" "}
                        {new Date(u.created_at).toLocaleDateString("en-KE", {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </div>
                      {approveErrors[u.id] && (
                        <p className="mt-2 text-xs text-destructive">
                          {approveErrors[u.id]}
                        </p>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <select
                        value={roleOverrides[u.id] ?? u.role}
                        onChange={(e) =>
                          setRoleOverrides((r) => ({
                            ...r,
                            [u.id]: e.target.value as UserRole,
                          }))
                        }
                        className="border border-input rounded-md px-2 py-1.5 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                      >
                        {ALL_ROLES.map((r) => (
                          <option key={r.value} value={r.value}>
                            {r.label}
                          </option>
                        ))}
                      </select>

                      <Button
                        size="sm"
                        onClick={() => handleApprove(u.id, u.role)}
                        disabled={approving === u.id}
                        style={{ backgroundColor: "#1a3a6b" }}
                        className="text-white"
                      >
                        {approving === u.id ? "Approving…" : "Approve"}
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* ── Active users tab ──────────────────────────────────────────────── */}
      {activeTab === "active" && (
        activeLoading ? (
          <div className="text-center py-12 text-gray-400">Loading users…</div>
        ) : activeError ? (
          <div className="text-center py-12 text-destructive">
            <p className="font-medium">Failed to load users</p>
            <p className="text-sm mt-1">{activeError}</p>
            <Button variant="outline" className="mt-4" onClick={fetchActiveUsers}>
              Retry
            </Button>
          </div>
        ) : activeUsers.length === 0 ? (
          <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-xl">
            <p className="text-gray-400 font-medium">No active users</p>
            <p className="text-gray-300 text-sm mt-1">
              Accounts will appear here once users activate their accounts
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {activeUsers.map((u) => (
              <div key={u.id} className="bg-white border border-gray-200 rounded-xl p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-gray-900">{u.full_name}</span>
                      <Badge variant="outline" className="text-xs">
                        @{u.username}
                      </Badge>
                      <Badge
                        variant={u.status === "active" ? "default" : "destructive"}
                        className="text-xs capitalize"
                      >
                        {u.status}
                      </Badge>
                    </div>
                    <div className="mt-1 text-sm text-gray-500 space-y-0.5">
                      <div>{u.email}</div>
                      <div>
                        {u.court_station} —{" "}
                        <span className="capitalize">{u.role}</span>
                      </div>
                    </div>
                    {suspendErrors[u.id] && (
                      <p className="mt-2 text-xs text-destructive">
                        {suspendErrors[u.id]}
                      </p>
                    )}
                  </div>

                  <div className="shrink-0">
                    {u.status === "active" ? (
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => handleUpdateStatus(u.id, "suspended")}
                        disabled={suspending === u.id}
                      >
                        {suspending === u.id ? "Suspending…" : "Suspend"}
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleUpdateStatus(u.id, "active")}
                        disabled={suspending === u.id}
                      >
                        {suspending === u.id ? "Reactivating…" : "Reactivate"}
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}
