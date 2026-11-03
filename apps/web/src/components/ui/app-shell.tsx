"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import type { ReactNode } from "react";
import Icon from "./icon";
import type { IconName } from "./icon";
import ThemeControl from "./theme-control";
import DataConnectionsControl from "./data-connections-control";
const navigation: {
  href: string;
  label: string;
  icon: IconName;
  children?: { href: string; label: string }[];
}[] = [
  { href: "/", label: "Naptár", icon: "calendar" },
  {
    href: "/training-planning",
    label: "Edzéstervezés",
    icon: "target",
    children: [
      { href: "/training-planning", label: "Tervezés lépései" },
      { href: "/planning-cycles", label: "Edzésterv és ciklusok" },
      { href: "/planning-goals", label: "Fejlődési célok" },
    ],
  },
  {
    href: "/training-options/locations",
    label: "Edzési lehetőségek",
    icon: "activity",
    children: [
      { href: "/training-options/locations", label: "Helyszínek" },
      { href: "/training-options/schedule", label: "Általános órarend" },
    ],
  },
  { href: "/nutrition", label: "Táplálkozás", icon: "activity" },
  { href: "/shopping", label: "Bevásárlás", icon: "cart" },
  {
    href: "/athlete-setup",
    label: "Személyes adatok",
    icon: "user",
    children: [
      { href: "/athlete-setup", label: "Sportolói felmérés" },
      { href: "/personal-response", label: "Személyes válaszadatok" },
    ],
  },
  { href: "/settings", label: "Beállítások", icon: "settings" },
];
export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname(),
    [compact, setCompact] = useState(false);
  const matches = (href: string) =>
    href === "/"
      ? pathname === "/"
      : pathname === href || pathname.startsWith(href + "/");
  const current = navigation.find(
    (item) =>
      matches(item.href) || item.children?.some((child) => matches(child.href)),
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
            <div key={item.href} className="pt-nav-group">
              <Link
                key={item.href}
                href={item.href}
                title={item.label}
                aria-current={
                  current?.href === item.href && !item.children
                    ? "page"
                    : undefined
                }
                aria-expanded={
                  item.children ? current?.href === item.href : undefined
                }
                aria-controls={
                  item.children ? `pt-subnav-${item.icon}` : undefined
                }
              >
                <Icon name={item.icon} />
                <span>{item.label}</span>
              </Link>
              {item.children && current?.href === item.href && (
                <div
                  className="pt-subnav"
                  id={`pt-subnav-${item.icon}`}
                  role="group"
                  aria-label={`${item.label} részei`}
                >
                  {item.children.map((child) => (
                    <Link
                      key={child.href}
                      href={child.href}
                      aria-current={matches(child.href) ? "page" : undefined}
                    >
                      {child.label}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>
        <div className="pt-nav-bottom pt-nav-tools">
          <Link href="/coach" prefetch={false} title="Részletes edzéslista">
            <Icon name="activity" />
            <span>Edzéslista</span>
          </Link>
          <button
            type="button"
            onClick={() => setCompact((x) => !x)}
            aria-label={compact ? "Menü kinyitása" : "Menü összecsukása"}
            title={compact ? "Menü kinyitása" : "Menü összecsukása"}
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
