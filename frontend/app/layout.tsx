import type { Metadata } from "next";
import { Analytics } from "@vercel/analytics/react";
import "./styles.css";

export const metadata: Metadata = {
  title: "Motif",
  description: "Explore lenses and ideas across psychological films.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <Analytics />
      </body>
    </html>
  );
}
