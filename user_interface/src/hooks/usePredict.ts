"use client";

import { useState } from "react";
import { PredictionRequest, PredictionReport } from "@/types/api";

export type PredictState = "idle" | "predicting" | "done" | "error";

export function usePredict() {
  const [state, setState] = useState<PredictState>("idle");
  const [report, setReport] = useState<PredictionReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setReport(null);
    setError(null);
    setState("idle");
  }

  async function predict(req: PredictionRequest) {
    setState("predicting");
    setError(null);
    setReport(null);

    try {
      // Route through Next.js proxy so the httpOnly sheria_auth cookie is
      // forwarded as a Bearer token to FastAPI server-side.
      const res = await fetch("/api/proxy/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
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

      const data: PredictionReport = await res.json();
      setReport(data);
      setState("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Prediction failed");
      setState("error");
    }
  }

  return { state, report, error, reset, predict };
}
