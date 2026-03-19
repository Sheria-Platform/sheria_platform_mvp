"use client";

import { ActiveUser } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState } from "./adminHelpers";

interface Props {
  deactivatedUsers: ActiveUser[];
  deactivatedLoading: boolean;
  deactivatedError: string;
  reactivating: string | null;
  reactivateErrors: Record<string, string>;
  fetchDeactivatedUsers: () => void;
  handleReactivate: (userId: string) => void;
  setProfileUser: (user: ActiveUser) => void;
}

export function DeactivatedTab({
  deactivatedUsers, deactivatedLoading, deactivatedError, reactivating, reactivateErrors,
  fetchDeactivatedUsers, handleReactivate, setProfileUser,
}: Props) {
  if (deactivatedLoading) {
    return <div className="text-center py-12 text-gray-400">Loading…</div>;
  }
  if (deactivatedError) {
    return <ErrorState message={deactivatedError} onRetry={fetchDeactivatedUsers} />;
  }
  if (deactivatedUsers.length === 0) {
    return (
      <EmptyState
        message="No deactivated accounts"
        sub="Suspended users will appear here"
      />
    );
  }

  return (
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
                  {u.court_station} — <span className="capitalize">{u.role}</span>
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
                className="text-judicial-navy"
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
  );
}
