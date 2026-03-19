"use client";

import { PendingUser, UserRole } from "@/types/api";
import { ALL_ROLES } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState } from "./adminHelpers";

export interface ApproveResult {
  activation_link: string;
  activation_token: string;
}

interface Props {
  pending: PendingUser[];
  loading: boolean;
  fetchError: string;
  approving: string | null;
  approveErrors: Record<string, string>;
  roleOverrides: Record<string, UserRole>;
  results: Record<string, ApproveResult>;
  copied: string | null;
  origin: string;
  fetchPending: () => void;
  handleApprove: (userId: string, requestedRole: UserRole) => void;
  setRoleOverrides: React.Dispatch<React.SetStateAction<Record<string, UserRole>>>;
  copyLink: (uid: string, link: string, ns: string) => void;
  setProfileUser: (user: PendingUser) => void;
}

export function PendingTab({
  pending, loading, fetchError, approving, approveErrors,
  roleOverrides, results, copied, origin,
  fetchPending, handleApprove, setRoleOverrides, copyLink, setProfileUser,
}: Props) {
  return (
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
                    className="text-judicial-navy"
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
                    className="bg-judicial-navy text-white hover:bg-judicial-navy-800"
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
  );
}
