import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
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
  title: "G1 Products - Visual Verification & Delivery Portal",
  description: "Báo cáo đối soát Barcode & Ảnh mặt trước bao bì tách chuẩn 100% cho Website",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className={`${geistSans.variable} ${geistMono.variable} dark`}>
      <body className="bg-[#090d16] text-slate-100 antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}
