import type { IconName } from "@/components/ui/icon";
export const NAVIGATION_EVENT = "paddletrainer:navigation";
export type NavigationLink = { href: string; label: string };
export type NavigationSection = NavigationLink & { icon: IconName; future?: boolean; children: NavigationLink[] };
export const navigation: NavigationSection[] = [
  { href: "/", label: "Naptár", icon: "calendar", children: [
    { href: "/", label: "Naptárnézet" }, { href: "/coach", label: "Edzésnapló" }, { href: "/personal-response", label: "Személyes válaszadatok" },
  ] },
  { href: "/training-planning", label: "Edzéstervezési alapadatok", icon: "user", children: [
    { href: "/training-planning#personal", label: "Személyes alapadatok" }, { href: "/training-planning#sports", label: "Sportelőélet" },
    { href: "/training-planning#goals", label: "Sportcélok és felkészülés" }, { href: "/training-planning#locations", label: "Edzéshelyszínek" },
    { href: "/training-planning#schedule", label: "Általános edzésrend" }, { href: "/training-planning#assessment", label: "Állapotfelmérés" },
  ] },
  { href: "/nutrition", label: "Táplálkozási opciók", icon: "activity", children: [
    { href: "/nutrition#body-goals", label: "Testsúlycél és testtömeg" }, { href: "/nutrition#body-history", label: "Testtömeg-előzmények" },
    { href: "/nutrition#preferences", label: "Preferenciák és igények" }, { href: "/nutrition#shopping-options", label: "Bevásárlási lehetőségek" },
  ] },
  { href: "/settings", label: "Általános beállítások", icon: "settings", children: [
    { href: "/settings#appearance", label: "Megjelenés / téma" }, { href: "/settings#data-connections", label: "Órás adatkapcsolatok" },
    { href: "/settings#calendar-connections", label: "Naptárkapcsolatok" }, { href: "/settings#language", label: "Nyelv" },
  ] },
];
const dataRoutes = ["/training-planning", "/athlete-setup", "/initial-assessment", "/strength-assessment", "/planning-cycles", "/planning-goals", "/training-options"];
export function activeSection(pathname: string) {
  return dataRoutes.some((r) => pathname === r || pathname.startsWith(r + "/")) ? "/training-planning" : pathname === "/nutrition" || pathname === "/shopping" ? "/nutrition" : pathname === "/settings" ? "/settings" : "/";
}
export function activeSubmenu(pathname: string, hash: string) {
  if (pathname === "/training-planning") return `/training-planning${hash || "#personal"}`;
  if (pathname === "/initial-assessment" || pathname === "/strength-assessment") return "/training-planning#assessment";
  if (pathname.startsWith("/training-options")) return pathname.endsWith("schedule") ? "/training-planning#schedule" : "/training-planning#locations";
  if (pathname === "/athlete-setup") return "/training-planning#personal";
  if (["/planning-goals", "/planning-cycles"].includes(pathname)) return "/training-planning#goals";
  return pathname + hash;
}
