"use client";

import { PredictionReport, RiskLevel } from "@/types/api";
import { cn } from "@/lib/utils";
import { TrendingUp, AlertTriangle, CheckCircle, Clock, Users, Scale } from "lucide-react";

interface Props {
  report: PredictionReport;
}

const RISK_CONFIG: Record<RiskLevel, { label: string; color: string; bg: string; border: string }> = {
  low:      { label: "Low Risk",      color: "text-green-700",  bg: "bg-green-50",  border: "border-green-100" },
  medium:   { label: "Medium Risk",   color: "text-amber-700",  bg: "bg-amber-50",  border: "border-amber-100" },
  high:     { label: "High Risk",     color: "text-orange-700", bg: "bg-orange-50", border: "border-orange-100" },
  critical: { label: "Critical Risk", color: "text-red-700",    bg: "bg-red-50",    border: "border-red-100" },
};

export function PredictionResultCard({ report }: Props) {
  const risk = RISK_CONFIG[report.risk_level] ?? RISK_CONFIG.medium;
  const confidencePct = Math.round(report.confidence * 100);

  return (
    <div className="bg-white border rounded-xl overflow-hidden shadow-sm">
      {/* Header */}
      <div className={cn("flex items-center gap-4 px-6 py-4 border-b", risk.bg, risk.border)}>
        <TrendingUp size={32} className={cn("shrink-0", risk.color)} />
        <div className="flex-1">
          <p className={cn("text-lg font-semibold", risk.color)}>
            {report.estimated_months_min}–{report.estimated_months_max} months estimated
          </p>
          <p className="text-sm text-gray-500">
            {risk.label} · Based on {report.similar_cases_found} similar case{report.similar_cases_found !== 1 ? "s" : ""}
          </p>
        </div>

        {/* Confidence ring */}
        <div className="relative size-14 shrink-0">
          <svg viewBox="0 0 36 36" className="rotate-[-90deg] size-14">
            <circle cx="18" cy="18" r="15.9" fill="none" stroke="#e5e7eb" strokeWidth="3" />
            <circle
              cx="18" cy="18" r="15.9"
              fill="none"
              className="stroke-judicial-navy"
              strokeWidth="3"
              strokeDasharray={`${confidencePct} ${100 - confidencePct}`}
              strokeDashoffset="0"
              strokeLinecap="round"
            />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-xs font-bold text-judicial-navy">
            {confidencePct}%
          </span>
        </div>
      </div>

      <div className="px-6 py-4 space-y-5">
        {/* Summary */}
        <p className="text-sm text-gray-700 leading-relaxed">{report.summary}</p>

        {/* Duration breakdown */}
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Duration Forecast
          </h3>
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-gray-50 rounded-lg px-4 py-3 text-center">
              <Clock size={16} className="mx-auto mb-1 text-gray-400" />
              <p className="text-xl font-bold text-gray-800">{report.estimated_months_min}</p>
              <p className="text-xs text-gray-400">Min months</p>
            </div>
            <div className="bg-gray-50 rounded-lg px-4 py-3 text-center">
              <Clock size={16} className="mx-auto mb-1 text-gray-400" />
              <p className="text-xl font-bold text-gray-800">{report.estimated_months_max}</p>
              <p className="text-xs text-gray-400">Max months</p>
            </div>
            <div className="bg-gray-50 rounded-lg px-4 py-3 text-center">
              <Users size={16} className="mx-auto mb-1 text-gray-400" />
              <p className="text-xl font-bold text-gray-800">{report.similar_cases_found}</p>
              <p className="text-xs text-gray-400">Similar cases</p>
            </div>
          </div>
        </section>

        {/* Key factors */}
        {report.key_factors.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Key Factors
            </h3>
            <ul className="space-y-1.5">
              {report.key_factors.map((factor, i) => (
                <li key={i} className="flex items-start gap-2">
                  <Scale size={14} className="text-judicial-navy mt-0.5 shrink-0 opacity-60" />
                  <span className="text-sm text-gray-700">{factor}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Risk badge */}
        <div className={cn("flex items-center gap-2 rounded-lg px-4 py-3 border", risk.bg, risk.border)}>
          {report.risk_level === "low" ? (
            <CheckCircle size={16} className={risk.color} />
          ) : (
            <AlertTriangle size={16} className={risk.color} />
          )}
          <span className={cn("text-sm font-medium", risk.color)}>{risk.label}</span>
          <span className="text-sm text-gray-500 ml-1">— {confidencePct}% model confidence</span>
        </div>
      </div>
    </div>
  );
}
