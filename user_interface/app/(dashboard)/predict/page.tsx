"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { PredictionResultCard } from "@/components/predict/PredictionResultCard";
import { usePredict } from "@/hooks/usePredict";
import { CaseComplexity, PredictionRequest } from "@/types/api";
import { TrendingUp } from "lucide-react";

const CASE_TYPES = [
  "Land Dispute",
  "Criminal",
  "Commercial",
  "Family / Matrimonial",
  "Constitutional",
  "Judicial Review",
  "Employment & Labour",
  "Succession / Probate",
  "Civil (General)",
  "Other",
];

const COURTS = [
  "Supreme Court",
  "Court of Appeal — Nairobi",
  "Court of Appeal — Mombasa",
  "High Court — Nairobi",
  "High Court — Mombasa",
  "High Court — Kisumu",
  "High Court — Nakuru",
  "High Court — Eldoret",
  "Environment & Land Court",
  "Employment & Labour Relations Court",
  "Magistrates Court",
];

const COMPLEXITIES: { value: CaseComplexity; label: string; desc: string }[] = [
  { value: "low",       label: "Low",       desc: "Straightforward facts, settled law" },
  { value: "medium",    label: "Medium",    desc: "Some contested issues or novel points" },
  { value: "high",      label: "High",      desc: "Complex facts, multiple legal issues" },
  { value: "very_high", label: "Very High", desc: "Constitutional, multi-party, or precedent-setting" },
];

const DEFAULT_FORM: PredictionRequest = {
  case_type: "Land Dispute",
  court: "High Court — Nairobi",
  parties_count: 2,
  complexity: "medium",
  description: "",
};

export default function PredictPage() {
  const { state, report, error, reset, predict } = usePredict();
  const [form, setForm] = useState<PredictionRequest>(DEFAULT_FORM);

  const isPredicting = state === "predicting";
  const canSubmit = form.case_type && form.court && form.parties_count >= 1 && !isPredicting;

  function handleReset() {
    setForm(DEFAULT_FORM);
    reset();
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold mb-1" style={{ color: "#1a3a6b" }}>
          Sheria Predict
        </h1>
        <p className="text-gray-500 text-sm">
          Forecast case duration and delay risk based on analogous historical cases in Kenya's court system.
        </p>
      </div>

      {/* Form */}
      <div className="bg-white border rounded-xl p-5 space-y-4">
        {/* Case type + court */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-500">Case Type</label>
            <select
              value={form.case_type}
              onChange={(e) => setForm((f) => ({ ...f, case_type: e.target.value }))}
              disabled={isPredicting}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            >
              {CASE_TYPES.map((ct) => (
                <option key={ct} value={ct}>{ct}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-500">Court</label>
            <select
              value={form.court}
              onChange={(e) => setForm((f) => ({ ...f, court: e.target.value }))}
              disabled={isPredicting}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            >
              {COURTS.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Parties count + complexity */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-500">Number of Parties</label>
            <input
              type="number"
              min={1}
              max={50}
              value={form.parties_count}
              onChange={(e) => setForm((f) => ({ ...f, parties_count: Math.max(1, Math.min(50, parseInt(e.target.value) || 1)) }))}
              disabled={isPredicting}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-500">Case Complexity</label>
            <select
              value={form.complexity}
              onChange={(e) => setForm((f) => ({ ...f, complexity: e.target.value as CaseComplexity }))}
              disabled={isPredicting}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            >
              {COMPLEXITIES.map((c) => (
                <option key={c.value} value={c.value}>{c.label} — {c.desc}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Description */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-500">
            Brief Case Description <span className="text-gray-300">(optional)</span>
          </label>
          <textarea
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            disabled={isPredicting}
            rows={3}
            maxLength={2000}
            placeholder="Describe key facts, legal issues, or special circumstances that may affect timeline…"
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 placeholder:text-gray-300 resize-none"
          />
          <p className="text-xs text-gray-300 text-right">{form.description.length}/2000</p>
        </div>

        <div className="flex gap-3">
          <Button
            onClick={() => predict(form)}
            disabled={!canSubmit}
            className="flex-1"
            style={{ backgroundColor: "#1a3a6b" }}
          >
            {isPredicting ? (
              <span className="flex items-center gap-2">
                <span className="size-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Analysing…
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <TrendingUp size={15} />
                Predict Duration
              </span>
            )}
          </Button>

          {state !== "idle" && (
            <Button variant="outline" onClick={handleReset} disabled={isPredicting}>
              Reset
            </Button>
          )}
        </div>
      </div>

      {/* Error */}
      {state === "error" && error && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Result */}
      {state === "done" && report && <PredictionResultCard report={report} />}
    </div>
  );
}
