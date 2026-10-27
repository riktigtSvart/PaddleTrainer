"use client";
import { useSyncExternalStore } from "react";
import { isSpeedUnit, speedUnitKey, speedUnits } from "@/lib/session-analysis/presentation";
import type { SpeedUnit } from "@/lib/session-analysis/presentation";

let memory: SpeedUnit = "km/h";
const eventName = "paddletrainer:speed-unit-changed";
function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener(eventName, callback);
  return () => { window.removeEventListener("storage", callback); window.removeEventListener(eventName, callback); };
}
function snapshot(): SpeedUnit {
  try { const stored = localStorage.getItem(speedUnitKey); return isSpeedUnit(stored) ? stored : memory; } catch { return memory; }
}
export function useSpeedUnit(): [SpeedUnit, (value: SpeedUnit) => void] {
  const unit = useSyncExternalStore(subscribe, snapshot, () => "km/h" as const);
  return [unit, value => {
    if (!isSpeedUnit(value)) return;
    memory = value;
    try { localStorage.setItem(speedUnitKey, value); } catch { /* Still works during this visit. */ }
    window.dispatchEvent(new Event(eventName));
  }];
}
export function SpeedUnitControl({ value, onChange }: { value: SpeedUnit; onChange: (value: SpeedUnit) => void }) {
  return <label className="pt-speed-unit">Sebesség egysége<select value={value} onChange={event => {
    if (isSpeedUnit(event.target.value)) onChange(event.target.value);
  }}>{speedUnits.map(unit => <option key={unit} value={unit}>{unit}</option>)}</select></label>;
}
