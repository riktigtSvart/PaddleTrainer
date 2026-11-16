import type { Location, SlotDetails } from "./contracts";
import { day } from "@/lib/planning-cycles/contracts";

export function scheduleDateProblem(start: string | null, end: string | null): string | null {
  const valid = (value: string) => { try { day(value); return value >= "1900-01-01" && value <= "2100-12-31"; } catch { return false; } };
  if (!start || !valid(start)) return "Add meg az általános órarend érvényes kezdődátumát 1900 és 2100 között.";
  if (end && !valid(end)) return "Az órarend érvényességének vége 1900 és 2100 közötti érvényes dátum legyen.";
  if (end && end < start) return "Az órarend érvényességének vége nem előzheti meg a kezdődátumot.";
  return null;
}

const clock = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
export function slotWindowMinutes(value: SlotDetails): number | null {
  if (!clock.test(value.start_time) || !clock.test(value.end_time)) return null;
  const minutes = (s: string) => Number(s.slice(0, 2)) * 60 + Number(s.slice(3));
  let span = minutes(value.end_time) - minutes(value.start_time) + (value.ends_next_day ? 1440 : 0);
  if (!value.ends_next_day && value.start_fold === 0 && value.end_fold === 1 && span <= 0 && span > -60) span += 60;
  return span > 0 && span <= 1440 ? span : null;
}
export function slotProblem(value: SlotDetails, locations?: Location[]): string | null {
  if (!clock.test(value.start_time) || !clock.test(value.end_time)) return "Add meg az időablak kezdését és befejezését.";
  const span = slotWindowMinutes(value);
  if (span === null) return "A befejezés legyen a kezdés után; éjfél átlépésekor jelöld, hogy a befejezés másnapra esik.";
  if (!Number.isInteger(value.max_minutes) || value.max_minutes < 1 || value.max_minutes > 1440)
    return "Az edzésre fordítható idő 1 és 1440 közötti egész perc legyen.";
  if (value.max_minutes > span)
    return `A ${value.start_time}–${value.end_time}${value.ends_next_day ? " (+1 nap)" : ""} időablak ${span} perc. A megadott ${value.max_minutes} perc nem fér bele. Adj meg legfeljebb ${span} percet, vagy bővítsd az időablakot.`;
  if (!value.location_ids.length) return "Válassz legalább egy helyszínt az időablakhoz.";
  if (locations && value.location_ids.some(id => !locations.some(l => l.id === id))) return "Egy kiválasztott helyszín már hiányzik a mentett helyszínek közül. Válassz helyette másikat.";
  return null;
}
