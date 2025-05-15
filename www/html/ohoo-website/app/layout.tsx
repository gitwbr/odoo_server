import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { MobileMenuProvider } from "@/components/MobileMenuContext";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ＭegaBoard ERP - 大圖產業數位化轉型的最佳夥伴",
  description: "專為大圖產業設計的ERP系統，提供計價報價、庫存管理、生產流程等全方位解決方案",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-TW">
      <body className={inter.className}>
        <MobileMenuProvider>
          {children}
        </MobileMenuProvider>
      </body>
    </html>
  );
}
