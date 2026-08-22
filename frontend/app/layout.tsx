import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { I18nProvider } from "@/lib/i18n/config";
import { ThemeProvider } from "@/lib/theme";
import { ReactQueryProvider } from "@/lib/react-query-client";
import { Toaster } from "@/components/ui/toast";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Saudi ERP",
  description: "Core Nucleus — Saudi ERP System",
  icons: {
    icon: [{ url: "/erp-icon.png", type: "image/png" }],
    shortcut: "/erp-icon.ico",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // lang/dir are set client-side by I18nProvider (locale preference lives in
  // localStorage, only known after hydration); "ar"/"rtl" here are just the
  // pre-hydration defaults so there's no flash of LTR content given Arabic
  // is the nucleus's primary locale (Phase 1 §5: "Arabic bilingual support").
  return (
    <html lang="ar" dir="rtl" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <ReactQueryProvider>
          <I18nProvider>
            <ThemeProvider>
              {children}
              <Toaster />
            </ThemeProvider>
          </I18nProvider>
        </ReactQueryProvider>
      </body>
    </html>
  );
}
