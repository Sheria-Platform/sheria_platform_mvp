import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function generateId(): string {
  return Math.random().toString(36).substring(2) + Date.now().toString(36);
}

export function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString("en-KE", {
    hour: "2-digit",
    minute: "2-digit",
  });
}
