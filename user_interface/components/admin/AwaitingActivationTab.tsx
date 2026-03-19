"use client";

import { ActiveUser, UserRole } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, formatDate } from "./adminHelpers";
import { ApproveResult } from "./PendingTab";

interface Props {
  approvedUsers: ActiveUser[];
  approvedLoading: boolean;
  approvedError: string;
  resending: string | null;
  resendErrors: Record<string, string>;
  resendResults: Record<string, ApproveResult>;
  copied: string | null;
  origin: string;
  fetchApprovedUsers: () => void;
  handleResendActivation: (userId: string, currentRole: UserRole) => void;
  copyLink: (uid: string, link: string, ns: string) => void;
  setProfileUser: (user: ActiveUser) => void;
}

export function AwaitingActivationTab({
  approvedUsers, approvedLoading, approvedError, resending, resendErrors,
  resendResults, copied, origin,
  fetchApprovedUsers, handleResendActivation, copyLink, setProfileUser,
}: Props) {
  if (approvedLoading) {
    return <div className="text-center py-12 text-gray-400">Loading…</div>;
  }
  if (approvedError) {
    return <ErrorState message={approvedError} onRetry={fetchApprovedUsers} />;
  }
  if (approvedUsers.length === 0) {
    return (
      <EmptyState
        message="No accounts awaiting activation"
        sub="All approved accounts have been activated"
      />
    );
  }

  return (
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
                  {u.court_station} — <span className="capitalize">{u.role}</span>
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
                className="text-judicial-navy"
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
  );
}
