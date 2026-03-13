import type { Metadata } from "next";
import Link from "next/link";
import { IBM_Plex_Sans, Space_Grotesk } from "next/font/google";

import { MobileTabBar } from "@/components/mobile-tab-bar";

import "./globals.css";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-body",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "700"],
  variable: "--font-display",
});

export const metadata: Metadata = {
  title: "FilmUltra",
  description: "Professional photo asset management for photographers and image-heavy teams.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className={`${plexSans.variable} ${spaceGrotesk.variable}`}>
        <header className="site-header">
          <div className="site-header-inner">
            <Link href="/" className="brand-mark">
              FilmUltra
            </Link>
            <nav className="site-nav">
              <Link href="/">图库</Link>
              <Link href="/people">人物</Link>
              <Link href="/people/review">待确认</Link>
            </nav>
          </div>
        </header>
        {children}
        <MobileTabBar />
      </body>
    </html>
  );
}
