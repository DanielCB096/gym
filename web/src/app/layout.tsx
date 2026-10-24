import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Centro Fit | Operación",
  description: "Panel operativo para el gimnasio Centro Fit.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}