import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CircuitMind AI",
  description:
    "Autonomous agentic procurement platform for PCBA manufacturing.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen font-mono antialiased">{children}</body>
    </html>
  );
}
