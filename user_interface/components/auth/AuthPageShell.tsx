import Image from "next/image";

interface AuthPageShellProps {
  /** Page-specific content rendered inside the white card. */
  children: React.ReactNode;
}

/**
 * Shared outer wrapper for all auth pages (login, register, activate).
 *
 * Renders the judicial-navy background, centred Sheria logo, application
 * title, and a white rounded card that wraps the page-specific content.
 * Eliminates the copy-pasted shell that previously existed in every auth page.
 */
export function AuthPageShell({ children }: AuthPageShellProps) {
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
        <div className="bg-white rounded-xl shadow-2xl p-8">{children}</div>
      </div>
    </div>
  );
}
