"use client";

import { ActiveUser } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, formatDate } from "./adminHelpers";

interface Props {
  activeUsers: ActiveUser[];
  activeLoading: boolean;
  activeError: string;
  suspending: string | null;
  suspendErrors: Record<string, string>;
  fetchActiveUsers: () => void;
  handleSuspend: (userId: string) => void;
  setProfileUser: (user: ActiveUser) => void;
}

export function ActiveUsersTab({
  activeUsers, activeLoading, activeError, suspending, suspendErrors,
  fetchActiveUsers, handleSuspend, setProfileUser,
}: Props) {
  if (activeLoading) {
    return <div className="text-center py-12 text-gray-400">Loading users…</div>;
  }
  if (activeError) {
    return <ErrorState message={activeError} onRetry={fetchActiveUsers} />;
  }
  if (activeUsers.length === 0) {
    return (
      <EmptyState
        message="No active users"
        sub="Accounts appear here once users activate their account"
      />
    );
  }

  return (
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
                  {u.court_station} — <span className="capitalize">{u.role}</span>
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
                        day: "numeric", month: "short", year: "numeric",
                        hour: "2-digit", minute: "2-digit",
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
                className="text-judicial-navy"
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
  );
}
