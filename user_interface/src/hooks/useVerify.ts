"use client";

import { useState } from "react";
import { DocumentType, VerificationReport } from "@/types/api";

export type VerifyState = "idle" | "verifying" | "done" | "error";

export function useVerify() {
  const [state, setState] = useState<VerifyState>("idle");
  const [report, setReport] = useState<VerificationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);

  function selectFile(f: File) {
    setFile(f);
    setReport(null);
    setError(null);
    setState("idle");
  }

  function reset() {
    setFile(null);
    setReport(null);
    setError(null);
    setState("idle");
  }

  async function verify(documentType: DocumentType, caseNumber: string) {
    if (!file) return;

    setState("verifying");
    setError(null);
    setReport(null);

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
      setReport(data);
      setState("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
      setState("error");
    }
  }

  return { state, report, error, file, selectFile, reset, verify };
}
