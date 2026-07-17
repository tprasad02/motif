import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Motif",
  description: "Explore themes and ideas across psychological films.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
