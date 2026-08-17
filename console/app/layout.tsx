import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "WebPilot-QA 可验证浏览器智能体控制台",
  description: "用于查看可验证浏览器智能体任务的受控控制台。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
