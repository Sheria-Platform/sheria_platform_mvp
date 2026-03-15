"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Button } from "@/components/ui/button";
import { VerificationReportCard } from "@/components/verify/VerificationReportCard";
import { useVerify } from "@/hooks/useVerify";
import { useVerifyHistory } from "@/hooks/useVerifyHistory";
import { DocumentType, VerificationActivity } from "@/types/api";
import { cn } from "@/lib/utils";
import { FileText, X, ShieldCheck, History, ChevronDown, ChevronUp } from "lucide-react";

const DOCUMENT_TYPES: { value: DocumentType; label: string }[] = [
  { value: "court_order", label: "Court Order" },
  { value: "judgment", label: "Judgment" },
  { value: "pleading", label: "Pleading" },
  { value: "affidavit", label: "Affidavit" },
];

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("en-KE", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function VerifyPage() {
  const { state, report, error, file, selectFile, reset, verify } = useVerify();
  const history = useVerifyHistory();
  const [documentType, setDocumentType] = useState<DocumentType>("court_order");
  const [caseNumber, setCaseNumber] = useState("");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted[0]) selectFile(accepted[0]);
    },
    [selectFile]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
    maxSize: 50 * 1024 * 1024,
    disabled: state === "verifying",
  });

  const isVerifying = state === "verifying";
  const canSubmit = !!file && !isVerifying;

  async function handleVerify() {
    await verify(documentType, caseNumber);
    history.refresh();
  }

  function toggleExpanded(id: number) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold mb-1" style={{ color: "#1a3a6b" }}>
          Sheria Verify
        </h1>
        <p className="text-gray-500 text-sm">
          Authenticate court documents — orders, judgments, pleadings, and affidavits —
          against Kenya Law Reports and fraud patterns.
        </p>
      </div>

      {/* Upload zone */}
      {!file ? (
        <div
          {...getRootProps()}
          className={cn(
            "border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors",
            isDragActive
              ? "border-blue-500 bg-blue-50"
              : "border-gray-300 hover:border-blue-400 hover:bg-gray-50"
          )}
        >
          <input {...getInputProps()} />
          <ShieldCheck size={40} className="mx-auto mb-3 text-gray-300" />
          <p className="text-sm font-medium text-gray-700">
            {isDragActive ? "Drop the PDF here" : "Drag & drop a court document (PDF)"}
          </p>
          <p className="text-xs text-gray-400 mt-1">PDF only · up to 50 MB</p>
        </div>
      ) : (
        <div className="bg-white border rounded-xl p-4 space-y-4">
          {/* Selected file */}
          <div className="flex items-center gap-3">
            <FileText size={20} className="text-blue-600 shrink-0" />
            <span className="text-sm text-gray-800 flex-1 truncate font-medium">
              {file.name}
            </span>
            <span className="text-xs text-gray-400">
              {(file.size / 1024).toFixed(0)} KB
            </span>
            {state !== "verifying" && (
              <button
                onClick={reset}
                className="text-gray-400 hover:text-gray-700 transition-colors"
                title="Remove file"
              >
                <X size={16} />
              </button>
            )}
          </div>

          {/* Form fields */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-500">Document Type</label>
              <select
                value={documentType}
                onChange={(e) => setDocumentType(e.target.value as DocumentType)}
                disabled={isVerifying}
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              >
                {DOCUMENT_TYPES.map((dt) => (
                  <option key={dt.value} value={dt.value}>
                    {dt.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-500">
                Case Number <span className="text-gray-300">(optional)</span>
              </label>
              <input
                type="text"
                value={caseNumber}
                onChange={(e) => setCaseNumber(e.target.value)}
                disabled={isVerifying}
                placeholder="e.g. HC MISC. APP. 123 OF 2025"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 placeholder:text-gray-300"
              />
            </div>
          </div>

          <Button
            onClick={handleVerify}
            disabled={!canSubmit}
            className="w-full"
            style={{ backgroundColor: "#1a3a6b" }}
          >
            {isVerifying ? (
              <span className="flex items-center gap-2">
                <span className="size-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Verifying…
              </span>
            ) : (
              "Verify Document"
            )}
          </Button>
        </div>
      )}

      {/* Error */}
      {state === "error" && error && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Report */}
      {state === "done" && report && <VerificationReportCard report={report} />}

      {/* History panel */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
          <History size={16} />
          <span>Verification History</span>
          {!history.loading && (
            <span className="text-xs text-gray-400 font-normal">
              ({history.activities.length})
            </span>
          )}
        </div>

        {history.loading && (
          <p className="text-xs text-gray-400">Loading history…</p>
        )}

        {!history.loading && history.error && (
          <p className="text-xs text-red-500">{history.error}</p>
        )}

        {!history.loading && !history.error && history.activities.length === 0 && (
          <p className="text-xs text-gray-400">No verifications yet.</p>
        )}

        {!history.loading &&
          history.activities.map((activity: VerificationActivity) => (
            <div key={activity.id} className="bg-white border rounded-xl overflow-hidden">
              <button
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
                onClick={() => toggleExpanded(activity.id)}
              >
                {/* Authentic badge */}
                <span
                  className={cn(
                    "shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full",
                    activity.authentic
                      ? "bg-green-100 text-green-700"
                      : "bg-red-100 text-red-700"
                  )}
                >
                  {activity.authentic ? "Authentic" : "Suspect"}
                </span>

                {/* Filename + meta */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">
                    {activity.filename || "Unnamed document"}
                  </p>
                  <p className="text-xs text-gray-400">
                    {activity.document_type.replace("_", " ")}
                    {activity.case_number ? ` · ${activity.case_number}` : ""}
                    {" · "}
                    {Math.round(activity.confidence * 100)}% confidence
                    {" · "}
                    {formatDate(activity.created_at)}
                  </p>
                </div>

                {/* Expand toggle */}
                {expandedId === activity.id ? (
                  <ChevronUp size={16} className="text-gray-400 shrink-0" />
                ) : (
                  <ChevronDown size={16} className="text-gray-400 shrink-0" />
                )}
              </button>

              {expandedId === activity.id && (
                <div className="border-t px-4 pb-4 pt-2">
                  <VerificationReportCard report={activity.report} />
                </div>
              )}
            </div>
          ))}
      </div>
    </div>
  );
}
