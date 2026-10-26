"use client";
import EventProfileEditor from "./event-profile-editor";
import { emptyProfile } from "@/lib/planning-cycles/contracts";
import type { Competition } from "@/lib/planning-cycles/contracts";
import {
  buttonClass,
  Field,
  secondaryClass,
  Select,
} from "@/components/planning-goals/fields";

export default function CompetitionEditor({
  value,
  change,
  refining = false,
  sport = "",
  structured = false,
}: {
  value: Competition[];
  change: (events: Competition[]) => void;
  refining?: boolean;
  sport?: string;
  structured?: boolean;
}) {
  function patch(index: number, values: Partial<Competition>) {
    change(value.map((c, i) => (i === index ? { ...c, ...values } : c)));
  }
  return (
    <div className="space-y-5">
      <p className="text-sm leading-6 text-zinc-300">
        A még bizonytalan versenyhez adj meg időablakot. A pontos dátum később
        új, megőrzött változatként rögzíthető.
      </p>
      {value.map((event, i) => (
        <fieldset
          key={event.key}
          className="space-y-4 rounded-xl border border-zinc-700 p-4"
        >
          <legend className="px-2 font-medium">{i + 1}. verseny</legend>
          <Field
            label="Verseny neve"
            name={`event.${i}.title`}
            value={event.title}
            maxLength={200}
            required
            onChange={(e) => patch(i, { title: e.target.value })}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <Select
              label="Dátum pontossága"
              name={`event.${i}.precision`}
              value={event.precision}
              onChange={(e) => {
                const precision = e.target.value as Competition["precision"];
                patch(i, {
                  precision,
                  ...(precision === "exact"
                    ? { end_date: event.start_date }
                    : {}),
                });
              }}
            >
              <option value="exact">Pontos versenynap</option>
              <option value="window">Közelítő időablak</option>
            </Select>
            <Select
              label="Verseny szerepe"
              name={`event.${i}.priority`}
              value={event.priority}
              onChange={(e) =>
                patch(i, {
                  priority: e.target.value as Competition["priority"],
                })
              }
            >
              <option value="main">Főverseny</option>
              <option value="supporting">Köztes / felkészülési verseny</option>
            </Select>
            <Field
              label={
                event.precision === "exact" ? "Versenynap" : "Időablak kezdete"
              }
              name={`event.${i}.start`}
              type="date"
              value={event.start_date}
              required
              onChange={(e) =>
                patch(i, {
                  start_date: e.target.value,
                  ...(event.precision === "exact"
                    ? { end_date: e.target.value }
                    : {}),
                })
              }
            />
            {event.precision === "window" && (
              <Field
                label="Időablak vége"
                name={`event.${i}.end`}
                type="date"
                value={event.end_date}
                required
                onChange={(e) => patch(i, { end_date: e.target.value })}
              />
            )}
          </div>
          {(structured || event.profile) && (
            <EventProfileEditor
              value={event.profile}
              sport={sport}
              index={i}
              change={(profile) => patch(i, { profile })}
            />
          )}
          {refining ? (
            <Select
              label="Verseny állapota"
              name={`event.${i}.status`}
              value={event.status}
              onChange={(e) =>
                patch(i, { status: e.target.value as Competition["status"] })
              }
            >
              <option value="planned">Tervezett</option>
              <option value="cancelled">Lemondott / elmaradt</option>
            </Select>
          ) : (
            <button
              type="button"
              className={secondaryClass}
              onClick={() => change(value.filter((_, n) => n !== i))}
            >
              Verseny eltávolítása a piszkozatból
            </button>
          )}
        </fieldset>
      ))}
      <button
        type="button"
        disabled={value.length >= 64}
        className={buttonClass}
        onClick={() =>
          change([
            ...value,
            {
              key: "event-" + crypto.randomUUID(),
              title: "",
              start_date: "",
              end_date: "",
              precision: "exact",
              priority: "main",
              status: "planned",
              ...(structured ? { profile: emptyProfile(sport) } : {}),
            },
          ])
        }
      >
        Verseny hozzáadása
      </button>
    </div>
  );
}
