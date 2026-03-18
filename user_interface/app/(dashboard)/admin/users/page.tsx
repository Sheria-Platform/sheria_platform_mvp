"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useChatStore } from "@/store/chatStore";
import { apiFetch } from "@/lib/api";
import { ALL_ROLES } from "@/lib/constants";
import { ActiveUser, AnalyticsPayload, PendingUser, UserRole } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { BarChart2 } from "lucide-react";
import AnalyticsDashboard, { AnalyticsDashboardSkeleton } from "@/components/admin/AnalyticsDashboard";

interface ApproveResult {
  /** Relative path e.g. `/activate?token=<uuid>` */
  activation_link: string;
  activation_token: string;
}

type Tab = "pending" | "approved" | "active" | "deactivated" | "analytics";
type AnyUser = ActiveUser | PendingUser;

/**
 * Admin-only page for managing judicial staff accounts.
 *
 * Four tabs:
 * - **Pending Requests**      — approve / assign role for new registrations.
 * - **Awaiting Activation**   — approved accounts where the user has not yet
 *                               clicked their activation link; admin can resend.
 * - **Active Users**          — fully active accounts; admin can deactivate.
 * - **Deactivated**           — suspended accounts; admin can reactivate.
 */
export default function AdminUsersPage() {
  const user = useChatStore((s) => s.user);
  const [activeTab, setActiveTab] = useState<Tab>("pending");

  // ── Pending tab ────────────────────────────────────────────────────────
  const [pending, setPending] = useState<PendingUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState("");
  const [approving, setApproving] = useState<string | null>(null);
  const [approveErrors, setApproveErrors] = useState<Record<string, string>>({});
  const [roleOverrides, setRoleOverrides] = useState<Record<string, UserRole>>({});
  const [results, setResults] = useState<Record<string, ApproveResult>>({});

  // ── Approved (not yet activated) tab ──────────────────────────────────
  const [approvedUsers, setApprovedUsers] = useState<ActiveUser[]>([]);
  const [approvedLoading, setApprovedLoading] = useState(true);
  const [approvedError, setApprovedError] = useState("");
  const [resending, setResending] = useState<string | null>(null);
  const [resendErrors, setResendErrors] = useState<Record<string, string>>({});
  const [resendResults, setResendResults] = useState<Record<string, ApproveResult>>({});

  // ── Active users tab ───────────────────────────────────────────────────
  const [activeUsers, setActiveUsers] = useState<ActiveUser[]>([]);
  const [activeLoading, setActiveLoading] = useState(true);
  const [activeError, setActiveError] = useState("");
  const [suspending, setSuspending] = useState<string | null>(null);
  const [suspendErrors, setSuspendErrors] = useState<Record<string, string>>({});

  // ── Deactivated tab ────────────────────────────────────────────────────
  const [deactivatedUsers, setDeactivatedUsers] = useState<ActiveUser[]>([]);
  const [deactivatedLoading, setDeactivatedLoading] = useState(true);
  const [deactivatedError, setDeactivatedError] = useState("");
  const [reactivating, setReactivating] = useState<string | null>(null);
  const [reactivateErrors, setReactivateErrors] = useState<Record<string, string>>({});

  // ── Analytics tab ──────────────────────────────────────────────────────
  const [analyticsData, setAnalyticsData] = useState<AnalyticsPayload | null>(null);
  const [loadingAnalytics, setLoadingAnalytics] = useState(false);
  const [analyticsError, setAnalyticsError] = useState("");
  const [analyticsFetched, setAnalyticsFetched] = useState(false);

  // ── Profile panel ───────────────────────────────────────────────────────
  const [profileUser, setProfileUser] = useState<AnyUser | null>(null);

  // ── Shared clipboard state ─────────────────────────────────────────────
  const [copied, setCopied] = useState<string | null>(null);
  const [origin, setOrigin] = useState("");
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setOrigin(window.location.origin);
    return () => { if (copyTimerRef.current) clearTimeout(copyTimerRef.current); };
  }, []);

  // ── Data fetchers ──────────────────────────────────────────────────────
  const fetchPending = useCallback(async () => {
    setLoading(true); setFetchError("");
    try { setPending(await apiFetch<PendingUser[]>("/api/proxy/admin/pending")); }
    catch (err) { setFetchError((err as Error).message); }
    finally { setLoading(false); }
  }, []);

  const fetchApprovedUsers = useCallback(async () => {
    setApprovedLoading(true); setApprovedError("");
    try { setApprovedUsers(await apiFetch<ActiveUser[]>("/api/proxy/admin/users?status=approved")); }
    catch (err) { setApprovedError((err as Error).message); }
    finally { setApprovedLoading(false); }
  }, []);

  const fetchActiveUsers = useCallback(async () => {
    setActiveLoading(true); setActiveError("");
    try { setActiveUsers(await apiFetch<ActiveUser[]>("/api/proxy/admin/users?status=active")); }
    catch (err) { setActiveError((err as Error).message); }
    finally { setActiveLoading(false); }
  }, []);

  const fetchDeactivatedUsers = useCallback(async () => {
    setDeactivatedLoading(true); setDeactivatedError("");
    try { setDeactivatedUsers(await apiFetch<ActiveUser[]>("/api/proxy/admin/users?status=suspended")); }
    catch (err) { setDeactivatedError((err as Error).message); }
    finally { setDeactivatedLoading(false); }
  }, []);

  const fetchAnalytics = useCallback(async () => {
    setLoadingAnalytics(true);
    setAnalyticsError("");
    try {
      const data = await apiFetch<AnalyticsPayload>("/api/proxy/admin/analytics");
      setAnalyticsData(data);
      setAnalyticsFetched(true);
    } catch (err) {
      setAnalyticsError((err as Error).message);
    } finally {
      setLoadingAnalytics(false);
    }
  }, []);

  useEffect(() => {
    if (user?.role === "admin") {
      fetchPending();
      fetchApprovedUsers();
      fetchActiveUsers();
      fetchDeactivatedUsers();
    }
  }, [user?.role, fetchPending, fetchApprovedUsers, fetchActiveUsers, fetchDeactivatedUsers]);

  if (user?.role !== "admin") {
    return (
      <div className="p-8 text-center text-gray-500">
        Access restricted to administrators.
      </div>
    );
  }

  // ── Action handlers ────────────────────────────────────────────────────

  async function handleApprove(userId: string, requestedRole: UserRole) {
    const role = roleOverrides[userId] ?? requestedRole;
    setApproving(userId);
    setApproveErrors((e) => ({ ...e, [userId]: "" }));
    try {
      const data = await apiFetch<ApproveResult>(`/api/proxy/admin/approve/${userId}`, {
        method: "POST",
        body: JSON.stringify({ role }),
      });
      setResults((r) => ({ ...r, [userId]: data }));
      setPending((p) => p.filter((u) => u.id !== userId));
      await fetchApprovedUsers();
    } catch (err) {
      setApproveErrors((e) => ({ ...e, [userId]: (err as Error).message }));
    } finally {
      setApproving(null);
    }
  }

  async function handleResendActivation(userId: string, currentRole: UserRole) {
    setResending(userId);
    setResendErrors((e) => ({ ...e, [userId]: "" }));
    try {
      // Re-calling approve regenerates the activation token and resends the email
      const data = await apiFetch<ApproveResult>(`/api/proxy/admin/approve/${userId}`, {
        method: "POST",
        body: JSON.stringify({ role: currentRole }),
      });
      setResendResults((r) => ({ ...r, [userId]: data }));
    } catch (err) {
      setResendErrors((e) => ({ ...e, [userId]: (err as Error).message }));
    } finally {
      setResending(null);
    }
  }

  async function handleSuspend(userId: string) {
    setSuspending(userId);
    setSuspendErrors((e) => ({ ...e, [userId]: "" }));
    try {
      await apiFetch(`/api/proxy/admin/users/${userId}/status`, {
        method: "POST",
        body: JSON.stringify({ status: "suspended" }),
      });
      await Promise.all([fetchActiveUsers(), fetchDeactivatedUsers()]);
    } catch (err) {
      setSuspendErrors((e) => ({ ...e, [userId]: (err as Error).message }));
    } finally {
      setSuspending(null);
    }
  }

  async function handleReactivate(userId: string) {
    setReactivating(userId);
    setReactivateErrors((e) => ({ ...e, [userId]: "" }));
    try {
      await apiFetch(`/api/proxy/admin/users/${userId}/status`, {
        method: "POST",
        body: JSON.stringify({ status: "active" }),
      });
      await Promise.all([fetchDeactivatedUsers(), fetchActiveUsers()]);
    } catch (err) {
      setReactivateErrors((e) => ({ ...e, [userId]: (err as Error).message }));
    } finally {
      setReactivating(null);
    }
  }

  function copyLink(uid: string, link: string, ns: string) {
    navigator.clipboard.writeText(`${origin}${link}`).then(() => {
      setCopied(`${ns}-${uid}`);
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setCopied(null), 2000);
    });
  }

  // ── Shared UI helpers ──────────────────────────────────────────────────

  function Field({ label, value }: { label: string; value: string }) {
    return (
      <div>
        <span className="text-xs text-gray-400 uppercase tracking-wide">{label}</span>
        <p className="text-sm text-gray-800 mt-0.5">{value}</p>
      </div>
    );
  }

  function StatusBadge({ status }: { status: string }) {
    const map: Record<string, string> = {
      active: "bg-green-100 text-green-700",
      approved: "bg-blue-100 text-blue-700",
      pending: "bg-amber-100 text-amber-800",
      suspended: "bg-red-100 text-red-700",
    };
    return (
      <span className={`text-xs px-2 py-0.5 rounded-full capitalize ${map[status] ?? "bg-gray-100 text-gray-600"}`}>
        {status}
      </span>
    );
  }

  function EmptyState({ message, sub }: { message: string; sub: string }) {
    return (
      <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-xl">
        <p className="text-gray-400 font-medium">{message}</p>
        <p className="text-gray-300 text-sm mt-1">{sub}</p>
      </div>
    );
  }

  function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
    return (
      <div className="text-center py-12 text-destructive">
        <p className="font-medium">Failed to load</p>
        <p className="text-sm mt-1">{message}</p>
        <Button variant="outline" className="mt-4" onClick={onRetry}>Retry</Button>
      </div>
    );
  }

  function formatDate(iso: string | undefined) {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString("en-KE", {
      day: "numeric", month: "short", year: "numeric",
    });
  }

  // ── Tab switching ──────────────────────────────────────────────────────

  function handleTabChange(key: Tab) {
    setActiveTab(key);
    if (key === "analytics" && !analyticsFetched) {
      fetchAnalytics();
    }
  }

  // ── Tab config ─────────────────────────────────────────────────────────

  const tabs: { key: Tab; label: string; count?: number; countColor: string }[] = [
    {
      key: "pending",
      label: "Pending Requests",
      count: pending.length || undefined,
      countColor: "bg-amber-100 text-amber-800",
    },
    {
      key: "approved",
      label: "Awaiting Activation",
      count: approvedUsers.length || undefined,
      countColor: "bg-blue-100 text-blue-700",
    },
    { key: "active", label: "Active Users", countColor: "" },
    {
      key: "deactivated",
      label: "Deactivated",
      count: deactivatedUsers.length || undefined,
      countColor: "bg-red-100 text-red-700",
    },
    { key: "analytics", label: "Analytics", countColor: "" },
  ];

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">User Management</h1>
        <p className="text-gray-500 mt-1 text-sm">
          Review registration requests and manage judicial staff accounts
        </p>
      </div>

      {/* ── Tab bar ───────────────────────────────────────────────────── */}
      <div className="mb-6 flex border-b border-gray-200">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => handleTabChange(t.key)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === t.key
                ? "border-[#1a3a6b] text-[#1a3a6b]"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.key === "analytics" && <BarChart2 className="w-4 h-4" />}
            {t.label}
            {t.count !== undefined && t.count > 0 && (
              <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${t.countColor}`}>
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Pending tab ───────────────────────────────────────────────── */}
      {activeTab === "pending" && (
        <>
          {Object.keys(results).length > 0 && (
            <div className="mb-6 space-y-2">
              <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
                Approved — Activation link also sent by email
              </h2>
              {Object.entries(results).map(([uid, result]) => (
                <div key={uid} className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-lg px-4 py-3">
                  <span className="text-sm text-green-800 flex-1 truncate font-mono">
                    {origin}{result.activation_link}
                  </span>
                  <Button size="sm" variant="outline" onClick={() => copyLink(uid, result.activation_link, "approve")}>
                    {copied === `approve-${uid}` ? "Copied!" : "Copy Link"}
                  </Button>
                </div>
              ))}
            </div>
          )}

          {loading ? (
            <div className="text-center py-12 text-gray-400">Loading requests…</div>
          ) : fetchError ? (
            <ErrorState message={fetchError} onRetry={fetchPending} />
          ) : pending.length === 0 ? (
            <EmptyState
              message="No pending requests"
              sub="All registration requests have been reviewed"
            />
          ) : (
            <div className="space-y-3">
              {pending.map((u) => (
                <div key={u.id} className="bg-white border border-gray-200 rounded-xl p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-gray-900">{u.full_name}</span>
                        <Badge variant="outline" className="text-xs">@{u.username}</Badge>
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
                          day: "numeric", month: "short", year: "numeric",
                          hour: "2-digit", minute: "2-digit",
                        })}
                      </div>
                      {approveErrors[u.id] && (
                        <p className="mt-2 text-xs text-destructive">{approveErrors[u.id]}</p>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setProfileUser(u)}
                        className="text-[#1a3a6b]"
                      >
                        View
                      </Button>
                      <select
                        value={roleOverrides[u.id] ?? u.role}
                        onChange={(e) =>
                          setRoleOverrides((r) => ({ ...r, [u.id]: e.target.value as UserRole }))
                        }
                        className="border border-input rounded-md px-2 py-1.5 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                      >
                        {ALL_ROLES.map((r) => (
                          <option key={r.value} value={r.value}>{r.label}</option>
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

      {/* ── Awaiting Activation tab ────────────────────────────────────── */}
      {activeTab === "approved" && (
        approvedLoading ? (
          <div className="text-center py-12 text-gray-400">Loading…</div>
        ) : approvedError ? (
          <ErrorState message={approvedError} onRetry={fetchApprovedUsers} />
        ) : approvedUsers.length === 0 ? (
          <EmptyState
            message="No accounts awaiting activation"
            sub="All approved accounts have been activated"
          />
        ) : (
          <div className="space-y-3">
            {Object.keys(resendResults).length > 0 && (
              <div className="mb-4 space-y-2">
                <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
                  New activation links generated — also sent by email
                </h2>
                {Object.entries(resendResults).map(([uid, result]) => (
                  <div key={uid} className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-lg px-4 py-3">
                    <span className="text-sm text-green-800 flex-1 truncate font-mono">
                      {origin}{result.activation_link}
                    </span>
                    <Button size="sm" variant="outline" onClick={() => copyLink(uid, result.activation_link, "resend")}>
                      {copied === `resend-${uid}` ? "Copied!" : "Copy Link"}
                    </Button>
                  </div>
                ))}
              </div>
            )}

            {approvedUsers.map((u) => (
              <div key={u.id} className="bg-white border border-gray-200 rounded-xl p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-gray-900">{u.full_name}</span>
                      <Badge variant="outline" className="text-xs">@{u.username}</Badge>
                      <span className="text-xs px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-700">
                        Awaiting activation
                      </span>
                      {u.staff_number && (
                        <span className="text-xs text-gray-400">#{u.staff_number}</span>
                      )}
                    </div>
                    <div className="mt-1 text-sm text-gray-500 space-y-0.5">
                      <div>{u.email}</div>
                      <div>
                        {u.court_station} —{" "}
                        <span className="capitalize">{u.role}</span>
                      </div>
                    </div>
                    <div className="mt-2 text-xs text-gray-400">
                      Approved: {formatDate(u.created_at)}
                    </div>
                    {resendErrors[u.id] && (
                      <p className="mt-2 text-xs text-destructive">{resendErrors[u.id]}</p>
                    )}
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setProfileUser(u)}
                      className="text-[#1a3a6b]"
                    >
                      View
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleResendActivation(u.id, u.role as UserRole)}
                      disabled={resending === u.id}
                    >
                      {resending === u.id ? "Sending…" : "Resend Link"}
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {/* ── Active users tab ──────────────────────────────────────────── */}
      {activeTab === "active" && (
        activeLoading ? (
          <div className="text-center py-12 text-gray-400">Loading users…</div>
        ) : activeError ? (
          <ErrorState message={activeError} onRetry={fetchActiveUsers} />
        ) : activeUsers.length === 0 ? (
          <EmptyState
            message="No active users"
            sub="Accounts appear here once users activate their account"
          />
        ) : (
          <div className="space-y-3">
            {activeUsers.map((u) => (
              <div key={u.id} className="bg-white border border-gray-200 rounded-xl p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-gray-900">{u.full_name}</span>
                      <Badge variant="outline" className="text-xs">@{u.username}</Badge>
                      <span className="text-xs px-1.5 py-0.5 rounded-full bg-green-100 text-green-700">
                        Active
                      </span>
                    </div>
                    <div className="mt-1 text-sm text-gray-500 space-y-0.5">
                      <div>{u.email}</div>
                      <div>
                        {u.court_station} —{" "}
                        <span className="capitalize">{u.role}</span>
                      </div>
                    </div>
                    <div className="mt-2 text-xs text-gray-400 space-y-0.5">
                      {u.activated_at && (
                        <div>Member since {formatDate(u.activated_at)}</div>
                      )}
                      <div>
                        Last login:{" "}
                        {u.last_login_at
                          ? new Date(u.last_login_at).toLocaleString("en-KE", {
                              day: "numeric",
                              month: "short",
                              year: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "—"}
                      </div>
                    </div>
                    {suspendErrors[u.id] && (
                      <p className="mt-2 text-xs text-destructive">{suspendErrors[u.id]}</p>
                    )}
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setProfileUser(u)}
                      className="text-[#1a3a6b]"
                    >
                      View
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => handleSuspend(u.id)}
                      disabled={suspending === u.id}
                    >
                      {suspending === u.id ? "Deactivating…" : "Deactivate"}
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {/* ── Deactivated tab ───────────────────────────────────────────── */}
      {activeTab === "deactivated" && (
        deactivatedLoading ? (
          <div className="text-center py-12 text-gray-400">Loading…</div>
        ) : deactivatedError ? (
          <ErrorState message={deactivatedError} onRetry={fetchDeactivatedUsers} />
        ) : deactivatedUsers.length === 0 ? (
          <EmptyState
            message="No deactivated accounts"
            sub="Suspended users will appear here"
          />
        ) : (
          <div className="space-y-3">
            {deactivatedUsers.map((u) => (
              <div key={u.id} className="bg-white border border-gray-200 rounded-xl p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-gray-900">{u.full_name}</span>
                      <Badge variant="outline" className="text-xs">@{u.username}</Badge>
                      <Badge variant="destructive" className="text-xs">Deactivated</Badge>
                      {u.staff_number && (
                        <span className="text-xs text-gray-400">#{u.staff_number}</span>
                      )}
                    </div>
                    <div className="mt-1 text-sm text-gray-500 space-y-0.5">
                      <div>{u.email}</div>
                      <div>
                        {u.court_station} —{" "}
                        <span className="capitalize">{u.role}</span>
                      </div>
                    </div>
                    {reactivateErrors[u.id] && (
                      <p className="mt-2 text-xs text-destructive">{reactivateErrors[u.id]}</p>
                    )}
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setProfileUser(u)}
                      className="text-[#1a3a6b]"
                    >
                      View
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleReactivate(u.id)}
                      disabled={reactivating === u.id}
                    >
                      {reactivating === u.id ? "Reactivating…" : "Reactivate"}
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {/* ── Analytics tab ─────────────────────────────────────────────── */}
      {activeTab === "analytics" && (
        loadingAnalytics ? (
          <AnalyticsDashboardSkeleton />
        ) : analyticsError ? (
          <div className="text-center py-12 text-red-500">
            <p>{analyticsError}</p>
            <Button variant="outline" onClick={fetchAnalytics} className="mt-4">
              Retry
            </Button>
          </div>
        ) : analyticsData ? (
          <AnalyticsDashboard data={analyticsData} />
        ) : null
      )}

      {/* ── Profile slide-over panel ───────────────────────────────────── */}
      {profileUser && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setProfileUser(null)}
          />
          {/* Panel */}
          <div className="relative w-full max-w-sm bg-white shadow-xl flex flex-col overflow-y-auto">
            {/* Header */}
            <div className="flex items-center justify-between p-5 border-b">
              <h2 className="text-lg font-semibold text-[#1a3a6b]">User Profile</h2>
              <button
                onClick={() => setProfileUser(null)}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
                aria-label="Close"
              >
                ✕
              </button>
            </div>

            {/* Avatar + name */}
            <div className="p-5 flex flex-col items-center gap-2 border-b">
              {profileUser.avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={profileUser.avatar_url}
                  alt={profileUser.full_name}
                  className="w-20 h-20 rounded-full object-cover"
                />
              ) : (
                <div className="w-20 h-20 rounded-full bg-[#1a3a6b] flex items-center justify-center text-white text-2xl font-bold">
                  {(profileUser.full_name || profileUser.username)[0].toUpperCase()}
                </div>
              )}
              <p className="font-semibold text-gray-900">{profileUser.full_name}</p>
              <p className="text-sm text-gray-500">@{profileUser.username}</p>
              <StatusBadge status={profileUser.status} />
            </div>

            {/* Details */}
            <div className="p-5 space-y-3">
              <Field label="Email" value={profileUser.email} />
              <Field label="Role" value={profileUser.role.charAt(0).toUpperCase() + profileUser.role.slice(1)} />
              <Field label="Court Station" value={profileUser.court_station} />
              {profileUser.staff_number && (
                <Field label="Staff No." value={profileUser.staff_number} />
              )}
              {profileUser.bio && (
                <Field label="Bio" value={profileUser.bio} />
              )}
              {profileUser.phone && (
                <Field label="Phone" value={profileUser.phone} />
              )}
              <Field label="Registered" value={formatDate(profileUser.created_at)} />
              {"activated_at" in profileUser && profileUser.activated_at && (
                <Field label="Activated" value={formatDate(profileUser.activated_at)} />
              )}
              {"last_login_at" in profileUser && (
                <Field
                  label="Last Login"
                  value={
                    profileUser.last_login_at
                      ? new Date(profileUser.last_login_at).toLocaleString("en-KE", {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "—"
                  }
                />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
