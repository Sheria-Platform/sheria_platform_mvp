"use client";

import { useState } from "react";
import { JobState } from "@/hooks/useIngestionJobs";
import { cn } from "@/lib/utils";
import { CheckCircle, XCircle, Loader2, Clock, FileText } from "lucide-react";

export function statusIcon(s: JobState["status"]) {
  if (s === "running") return <Loader2 size={14} className="text-blue-500 animate-spin shrink-0" />;
  if (s === "done") return <CheckCircle size={14} className="text-green-500 shrink-0" />;
  if (s === "failed") return <XCircle size={14} className="text-red-500 shrink-0" />;
  return <Clock size={14} className="text-gray-400 shrink-0" />;
}

export function statusPill(s: JobState["status"]) {
  const base = "text-xs px-2 py-0.5 rounded-full font-medium";
  if (s === "running") return <span className={cn(base, "bg-blue-50 text-blue-700")}>Running</span>;
  if (s === "done") return <span className={cn(base, "bg-green-50 text-green-700")}>Completed</span>;
  if (s === "failed") return <span className={cn(base, "bg-red-50 text-red-600")}>Failed</span>;
  return <span className={cn(base, "bg-gray-100 text-gray-500")}>Queued</span>;
}

export function formatTs(ts: number | null) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("en-KE", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDuration(s: number | null) {
  if (s == null) return "—";
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export function JobRow({ job }: { job: JobState }) {
  const [expanded, setExpanded] = useState(false);
  const hasStats = job.stats && Object.keys(job.stats).length > 0;

  return (
    <div
      className="border-b last:border-0 cursor-pointer hover:bg-gray-50 transition-colors"
      onClick={() => setExpanded((v) => !v)}
    >
      <div className="flex items-center gap-3 px-4 py-3">
        {statusIcon(job.status)}

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <FileText size={13} className="text-gray-400 shrink-0" />
            <span className="text-sm font-medium text-gray-800 truncate">
              {job.filename || job.s3_key}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5 truncate">{job.s3_key}</p>
        </div>

        <div className="hidden sm:flex items-center gap-6 text-xs text-gray-400 shrink-0">
          <span title="Started">{formatTs(job.started_at)}</span>
          <span title="Duration">{formatDuration(job.duration_s)}</span>
        </div>

        {statusPill(job.status)}
      </div>

      {expanded && (
        <div className="px-4 pb-3 pt-0 ml-5">
          {job.error && (
            <p className="text-xs text-red-600 mb-2 font-mono">{job.error}</p>
          )}
          {hasStats ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {[
                ["Files processed", job.stats.files_processed],
                ["Chunks created", job.stats.chunks_created],
                ["Vectors indexed", job.stats.vectors_indexed],
                ["Failed", job.stats.files_failed],
              ].map(([label, val]) => (
                <div key={label as string} className="bg-gray-50 rounded-lg px-3 py-2">
                  <p className="text-xs text-gray-400">{label as string}</p>
                  <p className="text-sm font-semibold text-gray-700 mt-0.5">
                    {val ?? "—"}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-400">No stats available yet.</p>
          )}
        </div>
      )}
    </div>
  );
}
