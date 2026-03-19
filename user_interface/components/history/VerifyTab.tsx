"use client";

import { useState } from "react";
import { useVerifyHistory } from "@/hooks/useVerifyHistory";
import { VerificationActivity } from "@/types/api";
import { VerificationReportCard } from "@/components/verify/VerificationReportCard";
import { cn } from "@/lib/utils";
import { ShieldCheck, ShieldX, Loader2, XCircle, ChevronDown, ChevronUp } from "lucide-react";
import { formatDate } from "./utils";

function VerifyRow({ activity }: { activity: VerificationActivity }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-b last:border-0">
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        {activity.authentic ? (
          <ShieldCheck size={15} className="text-green-500 shrink-0" />
        ) : (
          <ShieldX size={15} className="text-red-500 shrink-0" />
        )}

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-800 truncate">
            {activity.filename || "Unnamed document"}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
            {activity.document_type.replace("_", " ")}
            {activity.case_number ? ` · ${activity.case_number}` : ""}
            {" · "}
            {Math.round(activity.confidence * 100)}% confidence
            {" · "}
            {formatDate(activity.created_at)}
          </p>
        </div>

        <span
          className={cn(
            "shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full",
            activity.authentic ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
          )}
        >
          {activity.authentic ? "Authentic" : "Suspect"}
        </span>

        {expanded ? (
          <ChevronUp size={15} className="text-gray-400 shrink-0" />
        ) : (
          <ChevronDown size={15} className="text-gray-400 shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-4 pt-1">
          <VerificationReportCard report={activity.report} />
        </div>
      )}
    </div>
  );
}

export function VerifyTab() {
  const { activities, loading, error } = useVerifyHistory();

  return (
    <div className="flex-1 overflow-auto px-4 py-6 max-w-4xl mx-auto w-full">
      <p className="text-sm text-gray-500 mb-5">
        Every document authentication run is saved here for audit and review.
      </p>

      <div className="bg-white border rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-gray-400 gap-2">
            <Loader2 size={16} className="animate-spin" />
            <span className="text-sm">Loading verifications…</span>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-16 text-red-400">
            <XCircle size={32} className="mb-3 opacity-50" />
            <p className="text-sm">{error}</p>
          </div>
        ) : activities.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <ShieldCheck size={32} className="mb-3 opacity-30" />
            <p className="text-sm">No verifications yet. Use Sheria Verify to authenticate a document.</p>
          </div>
        ) : (
          activities.map((a) => <VerifyRow key={a.id} activity={a} />)
        )}
      </div>
    </div>
  );
}
