"use client";

import { useState } from "react";
import { getAuthToken } from "@/lib/auth";
import { PredictionRequest, PredictionReport } from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
      const token = getAuthToken();
      const res = await fetch(`${API_BASE}/api/v1/predict`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
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
