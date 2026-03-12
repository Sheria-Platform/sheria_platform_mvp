import { LoginForm } from "@/components/auth/LoginForm";

export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#1a3a6b]">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-white rounded-full mb-4">
            <span className="text-2xl font-bold text-[#1a3a6b]">S</span>
          </div>
          <h1 className="text-3xl font-bold text-white">Sheria Platform</h1>
          <p className="text-blue-200 mt-1 text-sm">
            Judicial Intelligence System — Kenya
          </p>
        </div>
        <div className="bg-white rounded-xl shadow-2xl p-8">
          <LoginForm />
        </div>
      </div>
    </div>
  );
}
