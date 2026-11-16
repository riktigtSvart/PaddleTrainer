"use client";
import { Field, Select } from "@/components/planning-goals/fields";

export function Choice({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Record<string, string>;
  onChange: (value: string) => void;
}) {
  return (
    <Select
      label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {Object.entries(options).map(([key, label]) => (
        <option key={key} value={key}>
          {label}
        </option>
      ))}
    </Select>
  );
}
export function DecimalField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string | null;
  onChange: (value: string | null) => void;
}) {
  return (
    <Field
      label={label}
      inputMode="decimal"
      placeholder="Nem ismert"
      maxLength={16}
      value={value ?? ""}
      onChange={(e) => {
        const raw = e.target.value.replace(",", ".");
        if (!raw) onChange(null);
        else if (/^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{0,6})?$/.test(raw))
          onChange(raw);
      }}
    />
  );
}
export function IntegerField({
  label,
  value,
  max,
  onChange,
}: {
  label: string;
  value: number | null;
  max: number;
  onChange: (value: number | null) => void;
}) {
  return (
    <Field
      label={label}
      type="number"
      min={0}
      max={max}
      step={1}
      placeholder="Nem ismert"
      value={value ?? ""}
      onChange={(e) => {
        if (!e.target.value) onChange(null);
        else {
          const n = Number(e.target.value);
          if (Number.isInteger(n) && n >= 0 && n <= max) onChange(n);
        }
      }}
    />
  );
}
export const unknown = "Még nem tudom";
