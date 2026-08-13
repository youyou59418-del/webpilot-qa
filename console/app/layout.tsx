import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "WebPilot-QA Console",
  description: "Read-only console for verifiable browser-agent runs.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
