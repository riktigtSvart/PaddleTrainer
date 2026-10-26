import Link from "next/link";
import AthleteWorkspace from "@/components/athlete-setup/workspace";
export const dynamic = "force-dynamic";
export default async function AthleteSetupPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string | string[] }>;
}) {
  const { tab } = await searchParams;
  const initialTab = tab === "calendar" || tab === "history" ? tab : "profile";
  return (
    <main className="mx-auto max-w-6xl space-y-8 px-5 py-7 sm:px-8 sm:py-10">
      <Link className="text-sm text-zinc-300 hover:text-teal-200" href="/">
        ← Napirend
      </Link>
      <header className="space-y-3">
        <p className="text-sm text-teal-200">
          PaddleTrainer · A személyre szabott felkészülés alapjai
        </p>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Sportolói felmérés és edzéslehetőségek
        </h1>
        <p className="max-w-3xl leading-7 text-zinc-300">
          Add meg a sportmúltadat, a jelenlegi kereteket és a ténylegesen
          elérhető időpontokat. A mért előzményeket órából vagy kézzel is
          kiegészítheted.
        </p>
      </header>
      <AthleteWorkspace key={initialTab} initialTab={initialTab} />
    </main>
  );
}
