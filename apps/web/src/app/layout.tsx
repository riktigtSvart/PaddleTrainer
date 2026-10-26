import type { Metadata } from "next";
import AppShell from "@/components/ui/app-shell";
import { themeBootstrap } from "@/lib/ui/theme";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "PaddleTrainer", template: "%s · PaddleTrainer" },
  description: "Napirend, edzéslehetőségek és személyre szabott felkészülés.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="hu" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
