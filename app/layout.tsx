import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "AgentCrashLab — Find the failure. Prove the fix.",
  description:
    "A local reliability lab for tool-using agents. Inspect, inject, reproduce, and verify.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
