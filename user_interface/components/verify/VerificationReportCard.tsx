"use client";

import { VerificationCheck, VerificationReport } from "@/types/api";
import { cn } from "@/lib/utils";
import { CheckCircle, XCircle, AlertTriangle, ShieldCheck, ShieldX } from "lucide-react";

interface Props {
  report: VerificationReport;
}

export function VerificationReportCard({ report }: Props) {
  const pct = Math.round(report.confidence * 100);

  return (
    <div className="bg-white border rounded-xl overflow-hidden shadow-sm">
      {/* Header verdict */}
      <div
        className={cn(
          "flex items-center gap-3 px-6 py-4",
          report.authentic ? "bg-green-50 border-b border-green-100" : "bg-red-50 border-b border-red-100"
        )}
      >
        {report.authentic ? (
          <ShieldCheck size={32} className="text-green-600 shrink-0" />
        ) : (
          <ShieldX size={32} className="text-red-600 shrink-0" />
        )}
        <div className="flex-1">
          <p
            className={cn(
              "text-lg font-semibold",
              report.authentic ? "text-green-800" : "text-red-800"
            )}
          >
            {report.authentic ? "Document Authentic" : "Document Not Verified"}
          </p>
          <p className="text-sm text-gray-500 capitalize">
            {report.document_type.replace("_", " ")} · Confidence {pct}%
          </p>
        </div>

        {/* Confidence ring */}
        <div className="relative size-14 shrink-0">
          <svg viewBox="0 0 36 36" className="rotate-[-90deg] size-14">
            <circle
              cx="18" cy="18" r="15.9"
              fill="none"
              stroke="#e5e7eb"
              strokeWidth="3"
            />
            <circle
              cx="18" cy="18" r="15.9"
              fill="none"
              stroke={report.authentic ? "#16a34a" : "#dc2626"}
              strokeWidth="3"
              strokeDasharray={`${pct} ${100 - pct}`}
              strokeDashoffset="0"
              strokeLinecap="round"
            />
          </svg>
          <span
            className={cn(
              "absolute inset-0 flex items-center justify-center text-xs font-bold",
              report.authentic ? "text-green-700" : "text-red-700"
            )}
          >
            {pct}%
          </span>
        </div>
      </div>

      <div className="px-6 py-4 space-y-5">
        {/* Summary */}
        <p className="text-sm text-gray-700 leading-relaxed">{report.summary}</p>

        {/* Extracted metadata */}
        {Object.keys(report.extracted_metadata).length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Extracted Metadata
            </h3>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              {Object.entries(report.extracted_metadata).map(([key, val]) => (
                <div key={key} className="col-span-1">
                  <dt className="text-xs text-gray-400 capitalize">{key.replace(/_/g, " ")}</dt>
                  <dd className="text-sm text-gray-800 font-medium truncate" title={val ?? undefined}>{val || "—"}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        {/* Verification checks */}
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
            Verification Checks
          </h3>
          <ul className="space-y-2">
            {report.verification_checks.map((vc: VerificationCheck, i: number) => (
              <li key={i} className="flex items-start gap-2.5">
                {vc.passed ? (
                  <CheckCircle size={16} className="text-green-500 mt-0.5 shrink-0" />
                ) : (
                  <XCircle size={16} className="text-red-500 mt-0.5 shrink-0" />
                )}
                <div>
                  <p className="text-sm font-medium text-gray-700">{vc.check}</p>
                  <p className="text-xs text-gray-400">{vc.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        {/* Risk flags */}
        {report.risk_flags.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Risk Flags
            </h3>
            <ul className="space-y-1">
              {report.risk_flags.map((flag: string, i: number) => (
                <li key={i} className="flex items-start gap-2">
                  <AlertTriangle size={14} className="text-amber-500 mt-0.5 shrink-0" />
                  <span className="text-sm text-gray-700">{flag}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
