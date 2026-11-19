import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

import Providers from "@/app/providers";

// Both families are open-licensed and served from src/app/fonts (see the README there).
const display = localFont({
  src: "./fonts/BigShouldersDisplay-latin.woff2",
  variable: "--font-display",
  weight: "100 900",
  display: "swap",
});
const body = localFont({
  src: "./fonts/SchibstedGrotesk-latin.woff2",
  variable: "--font-body",
  weight: "400 900",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Concert Radar",
  description: "Every show near you, ranked by the artists you follow.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${display.variable} ${body.variable} antialiased`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
