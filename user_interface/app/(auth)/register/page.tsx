"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { UserRole } from "@/types/api";

const ROLES: { value: UserRole; label: string }[] = [
  { value: "judge", label: "Judge" },
  { value: "magistrate", label: "Magistrate" },
  { value: "registrar", label: "Court Registrar" },
  { value: "clerk", label: "Judicial Clerk" },
];

const COURT_STATIONS = [
  "Supreme Court",
  "Court of Appeal Nairobi",
  "Court of Appeal Mombasa",
  "High Court Nairobi",
  "High Court Mombasa",
  "High Court Kisumu",
  "High Court Nakuru",
  "High Court Eldoret",
  "Milimani Commercial Courts",
  "Milimani Law Courts",
  "Other",
];

export default function RegisterPage() {
  const [form, setForm] = useState({
    username: "",
    email: "",
    full_name: "",
    court_station: "",
    role: "clerk" as UserRole,
    staff_number: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  function set(field: string, value: string) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.username || !form.email || !form.full_name || !form.court_station) {
      setError("Please fill in all required fields.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${API}/api/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Registration failed");
      setSuccess(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#1a3a6b] py-10">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="flex justify-center mb-4">
            <Image
              src="/sheria-logo.jpg"
              alt="Sheria Platform"
              width={200}
              height={64}
              className="h-16 w-auto object-contain"
              priority
            />
          </div>
          <h1 className="text-3xl font-bold text-white">Sheria Platform</h1>
          <p className="text-blue-200 mt-1 text-sm">
            Judicial Intelligence System — Kenya
          </p>
        </div>

        <div className="bg-white rounded-xl shadow-2xl p-8">
          {success ? (
            <div className="text-center space-y-4">
              <div className="w-14 h-14 rounded-full bg-green-100 flex items-center justify-center mx-auto">
                <svg className="w-7 h-7 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-gray-900">Request Submitted</h2>
              <p className="text-gray-600 text-sm">
                Your registration request has been received. A court administrator will review it
                and send you an activation link once approved.
              </p>
              <Link href="/login">
                <Button className="w-full mt-2" style={{ backgroundColor: "#1a3a6b" }}>
                  Back to Sign in
                </Button>
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <h2 className="text-xl font-semibold text-gray-900">Request Access</h2>
                <p className="text-sm text-gray-500 mt-1">
                  Submit your details for administrator approval
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="full_name">Full Name <span className="text-red-500">*</span></Label>
                <Input
                  id="full_name"
                  value={form.full_name}
                  onChange={(e) => set("full_name", e.target.value)}
                  placeholder="Hon. Jane Mwangi"
                  disabled={loading}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="username">Username <span className="text-red-500">*</span></Label>
                  <Input
                    id="username"
                    value={form.username}
                    onChange={(e) => set("username", e.target.value)}
                    placeholder="j.mwangi"
                    disabled={loading}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="staff_number">Staff Number</Label>
                  <Input
                    id="staff_number"
                    value={form.staff_number}
                    onChange={(e) => set("staff_number", e.target.value)}
                    placeholder="JSC-12345"
                    disabled={loading}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="email">Official Email <span className="text-red-500">*</span></Label>
                <Input
                  id="email"
                  type="email"
                  value={form.email}
                  onChange={(e) => set("email", e.target.value)}
                  placeholder="j.mwangi@judiciary.go.ke"
                  disabled={loading}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="role">Role <span className="text-red-500">*</span></Label>
                <select
                  id="role"
                  value={form.role}
                  onChange={(e) => set("role", e.target.value)}
                  className="w-full border border-input bg-background rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  disabled={loading}
                >
                  {ROLES.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="court_station">Court Station <span className="text-red-500">*</span></Label>
                <select
                  id="court_station"
                  value={form.court_station}
                  onChange={(e) => set("court_station", e.target.value)}
                  className="w-full border border-input bg-background rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  disabled={loading}
                >
                  <option value="">Select court station…</option>
                  {COURT_STATIONS.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>

              {error && (
                <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">
                  {error}
                </p>
              )}

              <Button
                type="submit"
                className="w-full"
                style={{ backgroundColor: "#1a3a6b" }}
                disabled={loading}
              >
                {loading ? "Submitting…" : "Submit Request"}
              </Button>

              <p className="text-center text-sm text-gray-500">
                Already have an account?{" "}
                <Link href="/login" className="font-medium hover:underline" style={{ color: "#1a3a6b" }}>
                  Sign in
                </Link>
              </p>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
