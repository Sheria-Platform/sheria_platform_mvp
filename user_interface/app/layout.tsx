import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sheria Platform",
  description: "AI-powered judicial intelligence for Kenya's court system",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
