import BodyWorkspace from "@/components/nutrition/body-workspace";
import MealWorkspace from "@/components/nutrition/meal-workspace";
export const metadata = { title: "Étrend és táplálkozás" };
export default function NutritionPage() {
  return <main className="pt-settings"><h1>Étrend és táplálkozás</h1><MealWorkspace /><details className="pt-meal-body"><summary>Testsúlycél és testtömeg-előzmények</summary><BodyWorkspace /></details></main>;
}
