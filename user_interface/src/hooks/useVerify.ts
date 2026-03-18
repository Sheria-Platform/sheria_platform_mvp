"use client";

import { useState, useRef } from "react";
import { DocumentType, VerificationReport } from "@/types/api";

export type VerifyState = "idle" | "verifying" | "done" | "error";

// Staged progress milestones that mirror the three backend pipeline steps:
// PDF text extraction → LLM metadata analysis → Qdrant cross-reference + fraud check.
const STAGES: { pct: number; label: string; ms: number }[] = [
  { pct: 10, label: "Uploading document…",                    ms: 0    },
  { pct: 30, label: "Extracting document text…",              ms: 700  },
  { pct: 55, label: "Analysing document metadata…",           ms: 2800 },
  { pct: 75, label: "Cross-referencing Kenya Law Reports…",   ms: 5500 },
  { pct: 88, label: "Running fraud pattern analysis…",        ms: 9000 },
];

export function useVerify() {
  const [state, setState] = useState<VerifyState>("idle");
  const [report, setReport] = useState<VerificationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [step, setStep] = useState("");
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  function clearTimers() {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }

  function startProgress() {
    clearTimers();
    setProgress(0);
    setStep("");
    STAGES.forEach(({ pct, label, ms }) => {
      const id = setTimeout(() => {
        setProgress(pct);
        setStep(label);
      }, ms);
      timers.current.push(id);
    });
  }

  function selectFile(f: File) {
    setFile(f);
    setReport(null);
    setError(null);
    setState("idle");
    setProgress(0);
    setStep("");
  }

  function reset() {
    clearTimers();
    setFile(null);
    setReport(null);
    setError(null);
    setState("idle");
    setProgress(0);
    setStep("");
  }

  async function verify(documentType: DocumentType, caseNumber: string) {
    if (!file) return;

    setState("verifying");
    setError(null);
    setReport(null);
    startProgress();

    const body = new FormData();
    body.append("file", file);
    body.append("document_type", documentType);
    body.append("case_number", caseNumber);

    try {
      // Route through Next.js proxy so the httpOnly sheria_auth cookie is
      // forwarded as a Bearer token to FastAPI server-side.
      const res = await fetch("/api/proxy/verify", {
        method: "POST",
        body,
      });

      if (!res.ok) {
        const text = await res.text();
        let message = `HTTP ${res.status}`;
        try {
          const json = JSON.parse(text);
          if (json.detail) message = json.detail;
        } catch {
          if (text) message = text;
        }
        throw new Error(message);
      }

      const data: VerificationReport = await res.json();
      clearTimers();
      setProgress(100);
      setStep("Verification complete");
      setReport(data);
      setState("done");
    } catch (err) {
      clearTimers();
      setProgress(0);
      setStep("");
      setError(err instanceof Error ? err.message : "Verification failed");
      setState("error");
    }
  }

  return { state, report, error, file, progress, step, selectFile, reset, verify };
}
