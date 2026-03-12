const SUGGESTED = [
  "What is the test for adverse possession in Kenya?",
  "Show binding precedents on right to fair trial",
  "Summarise the Mutunga constitutional reforms",
  "What damages apply in medical negligence cases?",
];

interface EmptyStateProps {
  onSelect: (q: string) => void;
}

export function EmptyState({ onSelect }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4">
      <div className="text-5xl mb-4">⚖️</div>
      <h2 className="text-xl font-semibold mb-2" style={{ color: "#1a3a6b" }}>
        Sheria Legal Research
      </h2>
      <p className="text-gray-500 text-sm mb-8 max-w-sm">
        Ask a legal research question. The system searches Kenya Law Reports,
        binding precedents, and statutes.
      </p>
      <div className="grid gap-2 w-full max-w-lg">
        {SUGGESTED.map((q) => (
          <button
            key={q}
            onClick={() => onSelect(q)}
            className="text-left px-4 py-2.5 rounded-lg border border-gray-200 hover:border-blue-300 hover:bg-blue-50 text-sm text-gray-700 transition-colors"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
