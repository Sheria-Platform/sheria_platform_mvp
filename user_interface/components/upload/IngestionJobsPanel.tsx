"use client";

import { useIngestionJobs, JobState } from "@/hooks/useIngestionJobs";
import { UploadFile } from "@/hooks/useUpload";
import { CheckCircle, XCircle, Loader2, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  files: UploadFile[];
}

const STATUS_ICON = {
  pending: <Clock size={15} className="text-gray-400 shrink-0" />,
  running: <Loader2 size={15} className="text-blue-500 animate-spin shrink-0" />,
  done: <CheckCircle size={15} className="text-green-500 shrink-0" />,
  failed: <XCircle size={15} className="text-red-500 shrink-0" />,
};

const STATUS_LABEL = {
  pending: "Queued",
  running: "Indexing…",
  done: "Indexed",
  failed: "Failed",
};

function JobRow({ file, job }: { file: UploadFile; job?: JobState }) {
  const st = job?.status ?? "pending";
  return (
    <div className="flex items-start gap-3 py-2.5 border-b last:border-0">
      {STATUS_ICON[st]}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-800 truncate">{file.file.name}</p>
        <p className={cn("text-xs mt-0.5", st === "failed" ? "text-red-500" : "text-gray-400")}>
          {st === "failed" && job?.error ? job.error : STATUS_LABEL[st]}
        </p>
        {st === "done" && job?.stats && Object.keys(job.stats).length > 0 && (
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1">
            {job.stats.vectors_indexed != null && (
              <span className="text-xs text-gray-400">
                {job.stats.vectors_indexed} vectors indexed
              </span>
            )}
            {job.stats.chunks_created != null && (
              <span className="text-xs text-gray-400">
                {job.stats.chunks_created} chunks
              </span>
            )}
            {job.stats.files_processed != null && (
              <span className="text-xs text-gray-400">
                {job.stats.files_processed} file(s) processed
              </span>
            )}
          </div>
        )}
      </div>
      <span
        className={cn(
          "text-xs px-2 py-0.5 rounded-full font-medium shrink-0",
          st === "done" && "bg-green-50 text-green-700",
          st === "running" && "bg-blue-50 text-blue-700",
          st === "pending" && "bg-gray-100 text-gray-500",
          st === "failed" && "bg-red-50 text-red-600"
        )}
      >
        {STATUS_LABEL[st]}
      </span>
    </div>
  );
}

export function IngestionJobsPanel({ files }: Props) {
  const doneFiles = files.filter((f) => f.status === "done" && f.jobId);
  const jobIds = doneFiles.map((f) => f.jobId!);
  const jobs = useIngestionJobs(jobIds);

  if (doneFiles.length === 0) return null;

  return (
    <div className="bg-white border rounded-xl p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-1">Ingestion Jobs</h3>
      <p className="text-xs text-gray-400 mb-3">
        Files are being parsed, chunked, and indexed into the Sheria knowledge base.
      </p>
      <div>
        {doneFiles.map((f) => (
          <JobRow key={f.jobId} file={f} job={jobs[f.jobId!]} />
        ))}
      </div>
    </div>
  );
}
