import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Korea ETF Monitor",
  description: "Real-time Korean ETF market dashboard with price, volume, and participant tracking",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
