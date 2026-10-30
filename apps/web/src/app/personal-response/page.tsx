import type { Metadata } from "next";
import DevelopmentNavigation from "@/components/ui/development-navigation";
import PersonalResponseWorkspace from "@/components/personal-response/workspace";
import "@/styles/personal-response.css";
export const metadata: Metadata = {
  title: "Személyes tapasztalat",
  description: "Bekötött edzések és saját visszajelzések leíró áttekintése.",
};
export default function PersonalResponsePage() {
  return (
    <main className="pt-pr-page pt-development-page">
      <DevelopmentNavigation personal />
      <header>
        <p className="pt-notice">Fejlődés · Saját visszajelzések</p>
        <h1>Személyes tapasztalat</h1>
        <p>
          Így értékelted a terhelést és a közérzetedet. Sportáganként, a
          visszajelzés időpontja szerint.
        </p>
      </header>
      <PersonalResponseWorkspace />
    </main>
  );
}
