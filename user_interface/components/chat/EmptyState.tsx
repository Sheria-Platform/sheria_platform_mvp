import Image from "next/image";

const SUGGESTED = [
  { label: "Adverse possession test", q: "What is the test for adverse possession in Kenya?" },
  { label: "Right to fair trial", q: "Show binding precedents on the right to fair trial" },
  { label: "Mutunga reforms", q: "Summarise the Mutunga constitutional reforms" },
  { label: "Medical negligence", q: "What damages apply in medical negligence cases?" },
];

interface EmptyStateProps {
  onSelect: (q: string) => void;
}

export function EmptyState({ onSelect }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4">
      <div className="mb-5">
        <Image
          src="/sheria-logo.jpg"
          alt="Sheria Platform"
          width={160}
          height={64}
          className="h-16 w-auto object-contain"
          priority
        />
      </div>
      <h2 className="text-2xl font-semibold text-gray-800 mb-2">
        How can I help you today?
      </h2>
      <p className="text-gray-500 text-sm mb-8 max-w-sm">
        Search Kenya Law Reports, binding precedents, statutes, and court records.
      </p>
      <div className="grid grid-cols-2 gap-3 w-full max-w-xl">
        {SUGGESTED.map(({ label, q }) => (
          <button
            key={q}
            onClick={() => onSelect(q)}
            className="text-left px-4 py-3 rounded-xl border border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm text-sm text-gray-700 transition-all"
          >
            <span className="font-medium text-gray-800 block mb-0.5">{label}</span>
            <span className="text-xs text-gray-400 line-clamp-2">{q}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
