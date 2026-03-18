"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Button } from "@/components/ui/button";
import { VerificationReportCard } from "@/components/verify/VerificationReportCard";
import { useVerify } from "@/hooks/useVerify";
import { DocumentType } from "@/types/api";
import { cn } from "@/lib/utils";
import { FileText, X, ShieldCheck } from "lucide-react";

const DOCUMENT_TYPES: { value: DocumentType; label: string }[] = [
  { value: "court_order", label: "Court Order" },
  { value: "judgment", label: "Judgment" },
  { value: "pleading", label: "Pleading" },
  { value: "affidavit", label: "Affidavit" },
];

export default function VerifyPage() {
  const { state, report, error, file, progress, step, selectFile, reset, verify } = useVerify();
  const [documentType, setDocumentType] = useState<DocumentType>("court_order");
  const [caseNumber, setCaseNumber] = useState("");

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
    maxSize: 20 * 1024 * 1024,
    disabled: state === "verifying",
  });

  const isVerifying = state === "verifying";
  const canSubmit = !!file && !isVerifying;

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
          <p className="text-xs text-gray-400 mt-1">PDF only · up to 20 MB</p>
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
            onClick={() => verify(documentType, caseNumber)}
            disabled={!canSubmit}
            className="w-full"
            style={{ backgroundColor: "#1a3a6b" }}
          >
            {isVerifying ? "Verifying…" : "Verify Document"}
          </Button>

          {isVerifying && (
            <div className="space-y-1.5 pt-1">
              <div className="flex justify-between items-center text-xs text-gray-500">
                <span>{step}</span>
                <span className="tabular-nums">{progress}%</span>
              </div>
              <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-700 ease-out"
                  style={{ width: `${progress}%`, backgroundColor: "#1a3a6b" }}
                />
              </div>
            </div>
          )}
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
    </div>
  );
}
