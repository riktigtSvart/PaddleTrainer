"use client";
import { useState } from 'react';
import { durationHMS, parseDurationHMS } from '@/lib/duration';

export default function DurationField({ label, value, onChange, onBlur, optional = false }: {
  label: string; value: number | null; onChange: (value: number | null) => void; onBlur?: () => void; optional?: boolean;
}) {
  const [editing, setEditing] = useState<{ value: number | null; text: string } | null>(null);
  const canonical = value === null ? '' : Number.isFinite(value) ? durationHMS(value) : '';
  const shown = editing && Object.is(editing.value, value) ? editing.text : canonical;
  const invalid = !Number.isFinite(value) && value !== null;
  return <label>{label}<input type="text" inputMode="text" autoComplete="off" spellCheck={false} placeholder="00:00:00" maxLength={11}
    aria-invalid={invalid || undefined} value={shown} onChange={e => {
      const text = e.target.value, parsed = parseDurationHMS(text);
      setEditing({ value: parsed, text }); onChange(parsed);
    }} onBlur={() => {
      if (!invalid) setEditing(null);
      onBlur?.();
    }} /><small>óra:perc:másodperc{optional ? ' · üresen opcionális' : ''}</small></label>;
}
