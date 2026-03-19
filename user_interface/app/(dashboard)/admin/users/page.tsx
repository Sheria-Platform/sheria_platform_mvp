"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useChatStore } from "@/store/chatStore";
import { apiFetch } from "@/lib/api";
import { ActiveUser, PendingUser, UserRole } from "@/types/api";
import { Field, StatusBadge, formatDate } from "@/components/admin/adminHelpers";
import { PendingTab, ApproveResult } from "@/components/admin/PendingTab";
import { AwaitingActivationTab } from "@/components/admin/AwaitingActivationTab";
import { ActiveUsersTab } from "@/components/admin/ActiveUsersTab";
import { DeactivatedTab } from "@/components/admin/DeactivatedTab";

type Tab = "pending" | "approved" | "active" | "deactivated";
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
            onClick={() => setActiveTab(t.key)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === t.key
                ? "border-judicial-navy text-judicial-navy"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.label}
            {t.count !== undefined && t.count > 0 && (
              <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${t.countColor}`}>
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Tab content ───────────────────────────────────────────────── */}
      {activeTab === "pending" && (
        <PendingTab
          pending={pending}
          loading={loading}
          fetchError={fetchError}
          approving={approving}
          approveErrors={approveErrors}
          roleOverrides={roleOverrides}
          results={results}
          copied={copied}
          origin={origin}
          fetchPending={fetchPending}
          handleApprove={handleApprove}
          setRoleOverrides={setRoleOverrides}
          copyLink={copyLink}
          setProfileUser={(u) => setProfileUser(u)}
        />
      )}
      {activeTab === "approved" && (
        <AwaitingActivationTab
          approvedUsers={approvedUsers}
          approvedLoading={approvedLoading}
          approvedError={approvedError}
          resending={resending}
          resendErrors={resendErrors}
          resendResults={resendResults}
          copied={copied}
          origin={origin}
          fetchApprovedUsers={fetchApprovedUsers}
          handleResendActivation={handleResendActivation}
          copyLink={copyLink}
          setProfileUser={(u) => setProfileUser(u)}
        />
      )}
      {activeTab === "active" && (
        <ActiveUsersTab
          activeUsers={activeUsers}
          activeLoading={activeLoading}
          activeError={activeError}
          suspending={suspending}
          suspendErrors={suspendErrors}
          fetchActiveUsers={fetchActiveUsers}
          handleSuspend={handleSuspend}
          setProfileUser={(u) => setProfileUser(u)}
        />
      )}
      {activeTab === "deactivated" && (
        <DeactivatedTab
          deactivatedUsers={deactivatedUsers}
          deactivatedLoading={deactivatedLoading}
          deactivatedError={deactivatedError}
          reactivating={reactivating}
          reactivateErrors={reactivateErrors}
          fetchDeactivatedUsers={fetchDeactivatedUsers}
          handleReactivate={handleReactivate}
          setProfileUser={(u) => setProfileUser(u)}
        />
      )}

      {/* ── Profile slide-over panel ───────────────────────────────────── */}
      {profileUser && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setProfileUser(null)}
          />
          <div className="relative w-full max-w-sm bg-white shadow-xl flex flex-col overflow-y-auto">
            <div className="flex items-center justify-between p-5 border-b">
              <h2 className="text-lg font-semibold text-judicial-navy">User Profile</h2>
              <button
                onClick={() => setProfileUser(null)}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
                aria-label="Close"
              >
                ✕
              </button>
            </div>

            <div className="p-5 flex flex-col items-center gap-2 border-b">
              {profileUser.avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={profileUser.avatar_url}
                  alt={profileUser.full_name}
                  className="w-20 h-20 rounded-full object-cover"
                />
              ) : (
                <div className="w-20 h-20 rounded-full bg-judicial-navy flex items-center justify-center text-white text-2xl font-bold">
                  {(profileUser.full_name || profileUser.username)[0].toUpperCase()}
                </div>
              )}
              <p className="font-semibold text-gray-900">{profileUser.full_name}</p>
              <p className="text-sm text-gray-500">@{profileUser.username}</p>
              <StatusBadge status={profileUser.status} />
            </div>

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
                          day: "numeric", month: "short", year: "numeric",
                          hour: "2-digit", minute: "2-digit",
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
