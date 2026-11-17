import MealWorkspace from "@/components/nutrition/meal-workspace";
export const metadata = { title: "Bevásárlás" };
export default function ShoppingPage() {
  return (
    <main className="pt-settings">
      <h1>Bevásárlás</h1>
      <MealWorkspace initialView="shopping" />
    </main>
  );
}
