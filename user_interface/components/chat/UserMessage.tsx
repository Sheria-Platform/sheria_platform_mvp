import { ChatMessage } from "@/types/chat";
import { formatTime } from "@/lib/utils";

export function UserMessage({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-end px-4 py-1">
      <div className="max-w-[75%]">
        <div
          className="text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm leading-relaxed"
          style={{ backgroundColor: "#1a3a6b" }}
        >
          {message.content}
        </div>
        <p className="text-xs text-gray-400 text-right mt-1">
          {formatTime(message.timestamp)}
        </p>
      </div>
    </div>
  );
}
