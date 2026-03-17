"use client";

import { useEffect, useRef, useState } from "react";
import { UserCircle, Camera, Loader2, CheckCircle } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { getAuthUser, setAuthUser } from "@/lib/auth";
import { useChatStore } from "@/store/chatStore";
import { UserProfile } from "@/types/api";
import { UserRole } from "@/types/api";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-KE", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function roleLabel(role: string) {
  return role.charAt(0).toUpperCase() + role.slice(1);
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ProfilePage() {
  const { user, setUser } = useChatStore();

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Edit form state
  const [fullName, setFullName] = useState("");
  const [staffNumber, setStaffNumber] = useState("");
  const [bio, setBio] = useState("");
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null);

  // Avatar state
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [avatarSrc, setAvatarSrc] = useState<string | null>(null);
  const [avatarUploading, setAvatarUploading] = useState(false);
  const [avatarError, setAvatarError] = useState<string | null>(null);

  // ── Load profile on mount ──────────────────────────────────────────────────
  useEffect(() => {
    async function load() {
      try {
        const data = await apiFetch<UserProfile>("/api/v1/auth/me");
        setProfile(data);
        setFullName(data.full_name ?? "");
        setStaffNumber(data.staff_number ?? "");
        setBio(data.bio ?? "");
        setPhone(data.phone ?? "");
        setAvatarSrc(data.avatar_presigned_url ?? null);
      } catch (err: unknown) {
        setLoadError(err instanceof Error ? err.message : "Failed to load profile");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // ── Save profile edits ─────────────────────────────────────────────────────
  async function handleSave() {
    setSaving(true);
    setSaveMsg(null);
    try {
      const updated = await apiFetch<UserProfile>("/api/v1/auth/me", {
        method: "PATCH",
        body: JSON.stringify({ full_name: fullName, staff_number: staffNumber, bio, phone }),
      });
      setProfile(updated);
      setSaveMsg({ ok: true, text: "Changes saved." });

      // Persist updated full_name to cookie + Zustand so sidebar reflects it
      const current = getAuthUser();
      if (current) {
        const next = { ...current, full_name: updated.full_name };
        setAuthUser(next);
        setUser(next);
      }
    } catch (err: unknown) {
      setSaveMsg({ ok: false, text: err instanceof Error ? err.message : "Save failed." });
    } finally {
      setSaving(false);
    }
  }

  // ── Avatar upload ──────────────────────────────────────────────────────────
  async function handleAvatarChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setAvatarUploading(true);
    setAvatarError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      // Route through Next.js proxy so the httpOnly sheria_auth cookie is
      // forwarded as a Bearer token server-side.
      const res = await fetch("/api/proxy/avatar", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const text = await res.text();
        let msg = `Upload failed (HTTP ${res.status})`;
        try { msg = JSON.parse(text).detail ?? msg; } catch { /* raw text */ }
        throw new Error(msg);
      }

      const data = (await res.json()) as { avatar_presigned_url: string | null };
      if (data.avatar_presigned_url) {
        setAvatarSrc(data.avatar_presigned_url);
        // Persist avatar key to cookie so it survives refresh
        const current = getAuthUser();
        if (current) {
          const next = { ...current, avatar_url: file.name };
          setAuthUser(next);
          setUser(next);
        }
      }
    } catch (err: unknown) {
      setAvatarError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setAvatarUploading(false);
      // reset input so same file can be re-selected
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-gray-400" size={32} />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="p-8 text-red-600 text-sm">
        Failed to load profile: {loadError}
      </div>
    );
  }

  const initials =
    (profile?.full_name ?? user?.username ?? "?")
      .split(" ")
      .map((w) => w[0])
      .join("")
      .slice(0, 2)
      .toUpperCase();

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      {/* ── Page header ─────────────────────────────────────────────── */}
      <h1 className="text-2xl font-semibold text-[#1a3a6b]">My Profile</h1>

      {/* ── Avatar section ──────────────────────────────────────────── */}
      <div className="flex items-center gap-5">
        <div className="relative shrink-0">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="w-20 h-20 rounded-full overflow-hidden border-2 border-gray-200 bg-[#1a3a6b] flex items-center justify-center text-white text-2xl font-bold hover:opacity-90 transition-opacity relative group"
            title="Change profile picture"
          >
            {avatarSrc ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={avatarSrc} alt="Avatar" className="w-full h-full object-cover" />
            ) : (
              <span>{initials}</span>
            )}
            {/* Camera icon overlay on hover */}
            <span className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity rounded-full">
              {avatarUploading ? (
                <Loader2 size={20} className="animate-spin text-white" />
              ) : (
                <Camera size={20} className="text-white" />
              )}
            </span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="hidden"
            onChange={handleAvatarChange}
          />
        </div>
        <div>
          <p className="font-medium text-gray-800">{profile?.full_name || profile?.username}</p>
          <p className="text-sm text-gray-500">{roleLabel(profile?.role ?? "")}</p>
          {avatarError && (
            <p className="text-xs text-red-600 mt-1">{avatarError}</p>
          )}
        </div>
      </div>

      {/* ── Read-only details ────────────────────────────────────────── */}
      <section className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4 uppercase tracking-wide">
          Account Details
        </h2>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div>
            <dt className="text-gray-500">Username</dt>
            <dd className="text-gray-800 font-medium">{profile?.username ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Email</dt>
            <dd className="text-gray-800 font-medium">{profile?.email ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Role</dt>
            <dd className="text-gray-800 font-medium">{roleLabel(profile?.role ?? "")}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Court Station</dt>
            <dd className="text-gray-800 font-medium">{profile?.court_station ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Status</dt>
            <dd className="text-gray-800 font-medium capitalize">{profile?.status ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Staff Number</dt>
            <dd className="text-gray-800 font-medium">{profile?.staff_number ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Member Since</dt>
            <dd className="text-gray-800 font-medium">{formatDate(profile?.created_at)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Activated</dt>
            <dd className="text-gray-800 font-medium">{formatDate(profile?.activated_at)}</dd>
          </div>
        </dl>
      </section>

      {/* ── Edit form ────────────────────────────────────────────────── */}
      <section className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4 uppercase tracking-wide">
          Edit Profile
        </h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-gray-600 mb-1" htmlFor="full_name">
              Full Name
            </label>
            <input
              id="full_name"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a3a6b]/30"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1" htmlFor="staff_number">
              Staff Number
            </label>
            <input
              id="staff_number"
              type="text"
              value={staffNumber}
              onChange={(e) => setStaffNumber(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a3a6b]/30"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1" htmlFor="bio">
              Bio
            </label>
            <textarea
              id="bio"
              rows={3}
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a3a6b]/30 resize-none"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1" htmlFor="phone">
              Phone
            </label>
            <input
              id="phone"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a3a6b]/30"
            />
          </div>

          <div className="flex items-center gap-3 pt-1">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 bg-[#1a3a6b] text-white text-sm px-4 py-2 rounded-md hover:bg-[#163060] transition-colors disabled:opacity-60"
            >
              {saving && <Loader2 size={14} className="animate-spin" />}
              Save Changes
            </button>
            {saveMsg && (
              <span
                className={`flex items-center gap-1 text-sm ${
                  saveMsg.ok ? "text-green-600" : "text-red-600"
                }`}
              >
                {saveMsg.ok && <CheckCircle size={14} />}
                {saveMsg.text}
              </span>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
