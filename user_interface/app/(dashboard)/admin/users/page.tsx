"use client";

import { useState, useEffect, useCallback } from "react";
import { useChatStore } from "@/store/chatStore";
import { apiFetch } from "@/lib/api";
import { PendingUser, UserRole } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const ROLES: { value: UserRole; label: string }[] = [
  { value: "judge", label: "Judge" },
  { value: "magistrate", label: "Magistrate" },
  { value: "registrar", label: "Court Registrar" },
  { value: "clerk", label: "Judicial Clerk" },
  { value: "admin", label: "Administrator" },
];

interface ApproveResult {
  activation_link: string;
  activation_token: string;
}

export default function AdminUsersPage() {
  const user = useChatStore((s) => s.user);
  const [pending, setPending] = useState<PendingUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState<string | null>(null);
  const [roleOverrides, setRoleOverrides] = useState<Record<string, UserRole>>({});
  const [results, setResults] = useState<Record<string, ApproveResult>>({});
  const [copied, setCopied] = useState<string | null>(null);

  const fetchPending = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch<PendingUser[]>("/api/v1/auth/pending");
      setPending(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchPending(); }, [fetchPending]);

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
    try {
      const data = await apiFetch<ApproveResult>(`/api/v1/auth/approve/${userId}`, {
        method: "POST",
        body: JSON.stringify({ role }),
      });
      setResults((r) => ({ ...r, [userId]: data }));
      setPending((p) => p.filter((u) => u.id !== userId));
    } catch {
      // ignore
    } finally {
      setApproving(null);
    }
  }

  async function copyLink(userId: string, link: string) {
    const base = window.location.origin;
    await navigator.clipboard.writeText(`${base}${link}`);
    setCopied(userId);
    setTimeout(() => setCopied(null), 2000);
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Registration Requests</h1>
        <p className="text-gray-500 mt-1 text-sm">
          Review and approve pending judicial staff access requests
        </p>
      </div>

      {/* Activation links from this session */}
      {Object.entries(results).length > 0 && (
        <div className="mb-6 space-y-2">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
            Approved — Share Activation Links
          </h2>
          {Object.entries(results).map(([uid, result]) => (
            <div key={uid} className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-lg px-4 py-3">
              <span className="text-sm text-green-800 flex-1 truncate font-mono">
                {window.location.origin}{result.activation_link}
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
      ) : pending.length === 0 ? (
        <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-xl">
          <p className="text-gray-400 font-medium">No pending requests</p>
          <p className="text-gray-300 text-sm mt-1">All registration requests have been reviewed</p>
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
                    Requested: {new Date(u.created_at).toLocaleDateString("en-KE", {
                      day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
                    })}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <select
                    value={roleOverrides[u.id] ?? u.role}
                    onChange={(e) =>
                      setRoleOverrides((r) => ({ ...r, [u.id]: e.target.value as UserRole }))
                    }
                    className="border border-input rounded-md px-2 py-1.5 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                  >
                    {ROLES.map((r) => (
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
    </div>
  );
}
