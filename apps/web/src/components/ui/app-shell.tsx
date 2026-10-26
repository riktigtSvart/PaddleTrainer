"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import type { ReactNode } from "react";
import Icon from "./icon";
import type { IconName } from "./icon";
import ThemeControl from "./theme-control";
import DataConnectionsControl from "./data-connections-control";
const navigation: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Napirend", icon: "calendar" },
  { href: "/planning-cycles", label: "Felkészülés", icon: "target" },
  { href: "/planning-goals", label: "Fejlődés", icon: "chart" },
  { href: "/athlete-setup", label: "Sportolói profil", icon: "user" },
  { href: "/shopping", label: "Bevásárlás", icon: "cart" },
  { href: "/settings", label: "Beállítások", icon: "settings" },
];
export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname(),
    [compact, setCompact] = useState(false);
  const current = navigation.find((item) =>
    item.href === "/" ? pathname === "/" : pathname.startsWith(item.href),
  );
  return (
    <div className={`pt-frame${compact ? " pt-compact" : ""}`}>
      <a className="pt-skip" href="#pt-main">
        Ugrás a tartalomhoz
      </a>
      <aside className="pt-sidebar">
        <Link href="/" className="pt-brand" aria-label="PaddleTrainer napirend">
          <Icon name="wave" />
          <span>PaddleTrainer</span>
        </Link>
        <nav aria-label="Fő navigáció">
          {navigation.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              title={item.label}
              aria-current={current?.href === item.href ? "page" : undefined}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>
        <div className="pt-nav-bottom">
          <Link href="/coach" prefetch={false} title="Részletes edzéslista">
            <Icon name="activity" />
            <span>Edzéslista</span>
          </Link>
          <button
            type="button"
            onClick={() => setCompact((x) => !x)}
            aria-label={compact ? "Menü kinyitása" : "Menü összecsukása"}
            aria-expanded={!compact}
          >
            <Icon name="menu" />
            <span>Menü mérete</span>
          </button>
        </div>
      </aside>
      <div className="pt-main-column">
        <header className="pt-appbar">
          <span className="pt-location">
            {current?.label ?? "Edzésrészletek"}
          </span>
          <div className="pt-appbar-actions">
            <ThemeControl />
            <DataConnectionsControl />
          </div>
        </header>
        <div id="pt-main" className="pt-page-content">
          {children}
        </div>
      </div>
    </div>
  );
}
