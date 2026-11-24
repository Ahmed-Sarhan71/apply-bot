import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ThemeToggle } from "./theme-toggle";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Job applications",
  description: "What you applied to, when, and where",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="flex min-h-full flex-col">
        {/* set the stored theme before paint, so dark mode doesn't flash light */}
        <script
          dangerouslySetInnerHTML={{
            __html: "try{if(localStorage.theme==='dark')document.documentElement.classList.add('dark')}catch(e){}",
          }}
        />
        <div className="fixed top-4 right-4 z-10">
          <ThemeToggle />
        </div>
        {children}
      </body>
    </html>
  );
}
