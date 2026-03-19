"use client";

import { useState } from "react";
import { usePredictHistory } from "@/hooks/usePredictHistory";
import { PredictionActivity, RiskLevel } from "@/types/api";
import { PredictionResultCard } from "@/components/predict/PredictionResultCard";
import { cn } from "@/lib/utils";
import { TrendingUp, Loader2, AlertTriangle, ChevronDown, ChevronUp } from "lucide-react";
import { formatDate } from "./utils";

const RISK_LABELS: Record<RiskLevel, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

const RISK_PILL_CLASSES: Record<RiskLevel, string> = {
  low:      "bg-green-100 text-green-700",
  medium:   "bg-amber-100 text-amber-700",
  high:     "bg-orange-100 text-orange-700",
  critical: "bg-red-100 text-red-700",
};

function PredictRow({ activity }: { activity: PredictionActivity }) {
  const [expanded, setExpanded] = useState(false);
  const risk = activity.risk_level ?? "medium";

  return (
    <div className="border-b last:border-0">
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <TrendingUp size={15} className="text-judicial-navy shrink-0 opacity-70" />

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-800 truncate">
            {activity.case_type} · {activity.court}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
            {activity.complexity} complexity · {activity.parties_count} parties
            {activity.estimated_months_min != null && activity.estimated_months_max != null
              ? ` · ${activity.estimated_months_min}–${activity.estimated_months_max} months`
              : ""}
            {" · "}
            {formatDate(activity.created_at)}
          </p>
        </div>

        {activity.risk_level && (
          <span className={cn("shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full", RISK_PILL_CLASSES[risk])}>
            {RISK_LABELS[risk]}
          </span>
        )}

        {expanded ? (
          <ChevronUp size={15} className="text-gray-400 shrink-0" />
        ) : (
          <ChevronDown size={15} className="text-gray-400 shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-4 pt-1">
          <PredictionResultCard report={activity.report} />
        </div>
      )}
    </div>
  );
}

export function PredictTab() {
  const { activities, loading, error } = usePredictHistory();

  return (
    <div className="flex-1 overflow-auto px-4 py-6 max-w-4xl mx-auto w-full">
      <p className="text-sm text-gray-500 mb-5">
        All case duration forecasts are saved here for reference and audit.
      </p>

      <div className="bg-white border rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-gray-400 gap-2">
            <Loader2 size={16} className="animate-spin" />
            <span className="text-sm">Loading predictions…</span>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-16 text-red-400">
            <AlertTriangle size={32} className="mb-3 opacity-50" />
            <p className="text-sm">{error}</p>
          </div>
        ) : activities.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <TrendingUp size={32} className="mb-3 opacity-30" />
            <p className="text-sm">No predictions yet. Use Sheria Predict to forecast a case.</p>
          </div>
        ) : (
          activities.map((a) => <PredictRow key={a.id} activity={a} />)
        )}
      </div>
    </div>
  );
}
