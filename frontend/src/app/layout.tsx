import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "@/components/ui/sonner";
import { CalendarIcon, ListIcon, SparklesIcon } from "lucide-react";
import "./globals.css";

// Geist and Geist_Mono come from next/font/google.
// Next.js downloads the fonts at build time and self-hosts them,
// so the browser makes no runtime request to Google.
const geistSans = Geist({
  // variable exposes each font as a CSS custom property, --font-geist-sans and --font-geist-mono.
  // Each call returns an object whose .variable property is a generated class name.
  // The layout usually puts those class names on <body>, which defines the CSS variables.
  // Your CSS or Tailwind config then uses them, for example font-family: var(--font-geist-sans).
  variable: "--font-geist-sans",
  // The subsets argument loads only the Latin glyphs, which keeps the font files small.
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// This uses Next.js's Metadata API. Next.js reads the exported metadata object
// and generates the <title> and <meta name="description"> tags in the page <head>.
// The title is what shows in the browser tab.
// The title and description are also what search engines and link previews use.
export const metadata: Metadata = {
  title: "Financial Reports Calendar",
  description: "Automated corporate financial reports and earnings calendar",
};

// In the App Router, app/layout.tsx is the root layout.
// It wraps every page in the app, so it holds the UI that stays the same across routes.

// It renders the <html> and <body> tags.
// Only the root layout may do this, and Next.js requires it.

// It renders <main>{children}</main>.
// children is whichever page.tsx matches the current URL, for example / or /watchlist.

// It mounts the <Toaster /> once, so toasts work on every page.

// Layouts persist across navigation.
// When you move between / and /watchlist, the header and body don't re-mount and don't lose state.
// Only children changes.
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} dark h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground font-sans selection:bg-zinc-800 selection:text-foreground">
        <header className="sticky top-0 z-40 w-full border-b border-border/40 bg-background/80 backdrop-blur-xl">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
            <div className="flex items-center gap-6">
              <Link
                href="/calendar"
                className="flex items-center gap-2.5 group"
              >
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500/20 via-blue-500/20 to-teal-500/20 border border-blue-500/30 flex items-center justify-center text-blue-400 group-hover:scale-105 transition-transform">
                  <CalendarIcon className="w-4 h-4" />
                </div>
                <div className="flex flex-col">
                  <span className="text-sm font-bold tracking-tight text-foreground flex items-center gap-1.5">
                    Earnings Calendar
                    <span className="text-[10px] font-semibold uppercase px-1.5 py-0.2 rounded bg-zinc-800 text-muted-foreground border border-zinc-700">
                      Live
                    </span>
                  </span>
                </div>
              </Link>

              <nav className="flex items-center gap-1 sm:gap-2">
                <Link
                  href="/calendar"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs sm:text-sm font-medium rounded-md text-foreground/80 hover:text-foreground hover:bg-accent transition-colors"
                >
                  <CalendarIcon className="w-3.5 h-3.5 text-muted-foreground" />
                  <span>Calendar</span>
                </Link>
                <Link
                  href="/watchlist"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs sm:text-sm font-medium rounded-md text-foreground/80 hover:text-foreground hover:bg-accent transition-colors"
                >
                  <ListIcon className="w-3.5 h-3.5 text-muted-foreground" />
                  <span>Watchlist</span>
                </Link>
              </nav>
            </div>

            <div className="flex items-center gap-2">
              <span className="hidden sm:flex items-center gap-1 text-[11px] text-muted-foreground">
                <SparklesIcon className="w-3 h-3 text-blue-400" />
                Alpha Vantage Auto-Sync
              </span>
            </div>
          </div>
        </header>

        <main className="flex-1 flex flex-col">{children}</main>
        <Toaster position="bottom-right" richColors />
      </body>
    </html>
  );
}
