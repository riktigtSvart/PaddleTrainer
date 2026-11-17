export const NUTRITION_CHANGED = 'paddletrainer:nutrition-changed';
export const nutritionChangeKey = (owner: string) => `paddletrainer.nutrition.changed.v1:${owner}`;
export function notifyNutrition(owner: string) {
  try { window.dispatchEvent(new CustomEvent(NUTRITION_CHANGED, { detail: { owner } })); } catch { /* A notification never reverses a confirmed save. */ }
  try { localStorage.setItem(nutritionChangeKey(owner), crypto.randomUUID()); } catch { /* Same-tab notification remains available. */ }
}
