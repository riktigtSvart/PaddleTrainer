import Link from "next/link";
export default function DevelopmentNavigation({
  personal = false,
}: {
  personal?: boolean;
}) {
  return (
    <nav className="pt-development-nav" aria-label="Fejlődés nézetei">
      <Link href="/planning-goals" aria-current={personal ? undefined : "page"}>
        Célok és mérések
      </Link>
      <Link
        href="/personal-response"
        aria-current={personal ? "page" : undefined}
      >
        Személyes tapasztalat
      </Link>
    </nav>
  );
}
