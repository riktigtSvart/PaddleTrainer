"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { ReactNode } from "react";
import { loadContext } from "@/lib/athlete-setup/client";
import Icon from "./icon";
import { navigation, activeSection, activeSubmenu, NAVIGATION_EVENT } from "@/lib/ui/navigation";
import ThemeControl from "./theme-control";
import DataConnectionsControl from "./data-connections-control";

const subscribeLanguage = () => () => {};
const subscribeNarrow = (callback: () => void) => { const media = window.matchMedia("(max-width: 700px)"); media.addEventListener("change", callback); return () => media.removeEventListener("change", callback); };
const subscribeNavigation = (callback: () => void) => { window.addEventListener("hashchange", callback); window.addEventListener(NAVIGATION_EVENT, callback); return () => { window.removeEventListener("hashchange", callback); window.removeEventListener(NAVIGATION_EVENT, callback); }; };
export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname(), router = useRouter();
  const [compact, setCompact] = useState(false), [mobileOpen, setMobileOpen] = useState(false);
  const narrow = useSyncExternalStore(subscribeNarrow, () => window.matchMedia("(max-width: 700px)").matches, () => false);
  const expanded = narrow ? mobileOpen : !compact;
  const main = useRef<HTMLDivElement>(null);
  const language = useSyncExternalStore(subscribeLanguage, () => navigator.language, () => "");
  const hash = useSyncExternalStore(subscribeNavigation, () => window.location.hash, () => "");
  const current = activeSection(pathname), activeChild = activeSubmenu(pathname, hash);
  useEffect(() => {
    if (!window.location.hash) main.current?.scrollTo?.({ top: 0 });
  }, [pathname]);
  useEffect(() => {
    if (pathname !== "/") return;
    const abort = new AbortController();
    loadContext(abort.signal).then((context) => {
      if (!abort.signal.aborted && context.profile === null) router.replace("/training-planning?onboarding=1");
    }).catch(() => { /* The calendar keeps its own visible loading/error state. */ });
    return () => abort.abort();
  }, [pathname, router]);
  return <div className={`pt-frame pt-app-shell${compact ? " pt-compact" : ""}${narrow && mobileOpen ? " pt-mobile-open" : ""}`}>
    <a className="pt-skip" href="#pt-main">Ugrás a tartalomhoz</a>
    <aside className="pt-sidebar">
      <Link href="/" className="pt-brand" aria-label="PaddleTrainer naptár"><Icon name="wave" /><span>PaddleTrainer</span></Link>
      <nav aria-label="Fő navigáció">{navigation.map((item) => <div className="pt-navigation-section" key={item.href}>
        <Link href={item.href} aria-label={item.label} title={`${item.label}${item.future ? " · későbbi modul" : ""}`} aria-current={current === item.href ? "page" : undefined} onClick={() => setMobileOpen(false)}>
          <Icon name={item.icon} /><span>{item.label}{item.future && <small>Későbbi modul</small>}</span>
        </Link>
        {current === item.href && <div className="pt-sidebar-subnav" aria-label={`${item.label} almenü`}>{item.children.map((child) => <Link key={child.href} href={child.href} aria-current={activeChild === child.href ? "page" : undefined} onClick={(e) => {
          setMobileOpen(false);
          const url = new URL(child.href, window.location.href);
          if (url.pathname === pathname && url.hash) { e.preventDefault(); if (window.location.hash !== url.hash) window.location.hash = url.hash; }
        }}>{child.label}</Link>)}</div>}
      </div>)}</nav>
      <div className="pt-nav-bottom pt-nav-tools"><button type="button" onClick={() => narrow ? setMobileOpen((v) => !v) : setCompact((v) => !v)} title={expanded ? "Menü összecsukása" : "Menü kinyitása"} aria-label={expanded ? "Menü összecsukása" : "Menü kinyitása"} aria-expanded={expanded}><Icon name="menu" /><span>Menü mérete</span></button></div>
    </aside>
    <div className="pt-main-column">
      <header className="pt-appbar" aria-label="Állandó fejléc">
        <span className="pt-location">{navigation.find((v) => v.href === current)?.label}</span>
        <div className="pt-appbar-actions">
          <ThemeControl compact />
          <DataConnectionsControl />
          <Link href="/shopping" className="pt-button" title="Bevásárlólista" aria-label="Bevásárlólista"><Icon name="cart" /></Link>
          <span title={`Nyelv: rendszer${language ? ` (${language})` : ""}. A többnyelvű felület későbbi lehetőség.`}><button type="button" className="pt-header-future" disabled aria-label="Nyelv · rendszer alapértelmezése · későbbi lehetőség"><Icon name="language" /></button></span>
        </div>
      </header>
      <div id="pt-main" ref={main} tabIndex={-1} className="pt-page-content">{children}</div>
    </div>
  </div>;
}
