import type { Metadata } from "next";
import AppShell from "@/components/ui/app-shell";
import { themeBootstrap } from "@/lib/ui/theme";
import "./globals.css";
import "@/styles/compact-workspace.css";
import "@/styles/training-planning.css";
import "@/styles/strength-inventory.css";
import "@/styles/initial-assessment.css";
import "@/styles/assessed-strength.css";
import "@/styles/guided-strength.css";
import "@/styles/session-analysis.css";
import "@/styles/application-shell.css";
import "@/styles/nutrition.css";

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
