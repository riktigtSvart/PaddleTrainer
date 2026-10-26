"use client";
import Link from "next/link";
import { loadDetail as loadCycle } from "@/lib/planning-cycles/client";
import type { Detail as CycleDetail } from "@/lib/planning-cycles/contracts";
import { Competitions } from "@/components/planning-cycles/program-details";
import { useEffect, useRef, useState } from "react";
import {
  getJSON,
  GoalHTTPError,
  loadPage,
  readPeriods,
  sendPending,
} from "@/lib/planning-goals/client";
import {
  PENDING_KEY,
  prepareRequest,
  readCatalog,
  readPending,
} from "@/lib/planning-goals/contracts";
import type { PendingRequest } from "@/lib/planning-goals/contracts";
import { dateLabel, resourceLabels } from "@/lib/planning-goals/labels";
import { RESOURCES } from "@/lib/planning-goals/types";
import type {
  ArtifactPage,
  Catalog,
  MacroArtifact,
  Period,
  ProtocolArtifact,
  Receipt,
  Resource,
} from "@/lib/planning-goals/types";
import ArtifactDetails from "./artifact-details";
import MacroForm from "./macro-form";
import ProtocolForm from "./protocol-form";
import { AssessmentForm, MeasurementForm } from "./measurement-form";
import { buttonClass, Card, Message, secondaryClass, Select } from "./fields";

type Loaded = {
  catalog: Catalog;
  periods: Period[];
  pages: Record<Resource, ArtifactPage>;
};
function savedLabel(receipt: Receipt) {
  const artifact = receipt.artifact;
  if ("sources" in artifact && "revision" in artifact.proposal) {
    const id =
      "macrocycle_period_id" in artifact.proposal
        ? artifact.proposal.macrocycle_period_id
        : artifact.proposal.mesocycle_period_id;
    const title =
      [...artifact.sources.hierarchy, ...artifact.sources.mesocycles].find(
        (p) => p.period_id === id,
      )?.title ?? "Ciklus";
    return `${title} · ${artifact.proposal.revision}. verzió · ${dateLabel(receipt.durable_available_at)}`;
  }
  if ("proposal" in artifact && "value" in artifact.proposal)
    return `${artifact.proposal.endpoint_key}: ${artifact.proposal.value} · ${dateLabel(receipt.durable_available_at)}`;
  return dateLabel(receipt.durable_available_at);
}
export default function GoalWorkspace({
  initialPeriod,
  initialCycle = "",
}: {
  initialPeriod: string;
  initialCycle?: string;
}) {
  const [cycleContext, setCycleContext] = useState<CycleDetail | null>(null);
  const [cycleError, setCycleError] = useState("");
  const [loaded, setLoaded] = useState<Loaded | null>(null),
    [loadError, setLoadError] = useState("");
  const [reload, setReload] = useState(0),
    [periodId, setPeriodId] = useState(initialPeriod);
  const [resource, setResource] = useState<Resource>("macrocycle-plans");
  const [selected, setSelected] = useState<Partial<Record<Resource, string>>>(
    {},
  );
  const [macroId, setMacroId] = useState(""),
    [protocolId, setProtocolId] = useState("");
  const [creating, setCreating] = useState(false),
    [base, setBase] = useState<
      Receipt<MacroArtifact | ProtocolArtifact> | undefined
    >();
  const [pending, setPending] = useState<PendingRequest | null>(null),
    [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  const [rejected, setRejected] = useState(false),
    [success, setSuccess] = useState("");
  const [paging, setPaging] = useState(false);
  const sending = useRef(false);
  const initialised = useRef(false);
  const statusArea = useRef<HTMLDivElement>(null);
  function focusStatus() {
    requestAnimationFrame(() => {
      statusArea.current?.scrollIntoView({
        block: "start",
        behavior: "smooth",
      });
      statusArea.current?.focus({ preventScroll: true });
    });
  }
  function report(message: string) {
    setFailure(message);
    focusStatus();
  }

  useEffect(() => {
    if (!initialCycle) return;
    const controller = new AbortController();
    loadCycle(initialCycle, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setCycleContext(result);
          setCycleError("");
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setCycleError(
            error instanceof Error
              ? error.message
              : "A versenyadatok betöltése nem sikerült.",
          );
      });
    return () => controller.abort();
  }, [initialCycle, reload]);
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const [catalog, periods, ...pages] = await Promise.all([
          getJSON("catalog", controller.signal).then(readCatalog),
          getJSON("periods", controller.signal).then(readPeriods),
          ...RESOURCES.map((key) => loadPage(key, 0, controller.signal)),
        ]);
        if (!controller.signal.aborted) {
          if (!initialised.current) {
            const initial = (periods as Period[]).find(
              (p) => p.id === initialPeriod,
            );
            if (initial?.period_type === "MESOCYCLE")
              setResource("mesocycle-protocols");
            initialised.current = true;
          }
          setLoaded({
            catalog: catalog as Catalog,
            periods: periods as Period[],
            pages: Object.fromEntries(
              RESOURCES.map((key, index) => [key, pages[index]]),
            ) as Record<Resource, ArtifactPage>,
          });
          setLoadError("");
        }
      } catch (error) {
        if (!controller.signal.aborted)
          setLoadError(
            error instanceof Error
              ? error.message
              : "Az adatok betöltése nem sikerült.",
          );
      }
    }
    void load();
    return () => controller.abort();
  }, [reload, initialPeriod]);
  useEffect(() => {
    // Hydration starts with the same empty state as SSR. Storage is an external browser source.
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try {
        const value = sessionStorage.getItem(PENDING_KEY);
        if (value) {
          setPending(readPending(value));
          setFailure(
            "Korábbi függő mentési kérés található. Ugyanaz a kérés újraküldhető az eredmény ellenőrzéséhez.",
          );
        }
      } catch {
        setFailure(
          "A korábbi függő mentési kérés nem olvasható. Frissítés előtt ellenőrizd a mentett előzményeket.",
        );
      }
    });
    return () => {
      active = false;
    };
  }, []);

  async function send(request: PendingRequest) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setFailure("");
    setSuccess("");
    setRejected(false);
    focusStatus();
    try {
      // Save before sending. Refresh/reconnect keeps the exact body and measurement UUID.
      sessionStorage.setItem(PENDING_KEY, JSON.stringify(request));
      setPending(request);
      const receipt = await sendPending(request);
      try {
        sessionStorage.removeItem(PENDING_KEY);
      } catch {
        /* Identical retry remains safe. */
      }
      setLoaded((previous) =>
        previous
          ? {
              ...previous,
              pages: {
                ...previous.pages,
                [request.resource]: {
                  ...previous.pages[request.resource],
                  items: [
                    receipt,
                    ...previous.pages[request.resource].items.filter(
                      (item) =>
                        item.artifact.artifact_id !==
                        receipt.artifact.artifact_id,
                    ),
                  ],
                },
              },
            }
          : previous,
      );
      setSelected((previous) => ({
        ...previous,
        [request.resource]: receipt.artifact.artifact_id,
      }));
      setPending(null);
      setCreating(false);
      setBase(undefined);
      setSuccess(
        receipt.reused
          ? "A korábban mentett, azonos kérés eredménye visszaállítva."
          : "A szerver igazolta a tartós mentést. Az eredmény megjelent az előzményekben.",
      );
    } catch (error) {
      setFailure(
        error instanceof Error
          ? error.message
          : "A mentés eredménye nem igazolható.",
      );
      setRejected(
        error instanceof GoalHTTPError &&
          [400, 403, 404, 405, 409, 413, 415, 422].includes(error.status),
      );
    } finally {
      setBusy(false);
      sending.current = false;
      focusStatus();
    }
  }
  function submit(proposal: unknown) {
    if (pending || sending.current) return;
    try {
      void send(prepareRequest(resource, proposal));
    } catch (error) {
      setFailure(
        error instanceof Error
          ? error.message
          : "A kérés előkészítése nem sikerült.",
      );
    }
  }
  async function more() {
    if (!loaded || paging) return;
    const key = resource,
      page = loaded.pages[key];
    setPaging(true);
    try {
      const next = await loadPage(key, page.offset + 25);
      setLoaded((previous) =>
        previous
          ? {
              ...previous,
              pages: {
                ...previous.pages,
                [key]: {
                  ...next,
                  items: [
                    ...previous.pages[key].items,
                    ...next.items.filter(
                      (item) =>
                        !previous.pages[key].items.some(
                          (existing) =>
                            existing.artifact.artifact_id ===
                            item.artifact.artifact_id,
                        ),
                    ),
                  ],
                },
              },
            }
          : previous,
      );
    } catch (error) {
      setFailure(
        error instanceof Error
          ? error.message
          : "A további verziók betöltése nem sikerült.",
      );
    } finally {
      setPaging(false);
    }
  }
  function changeTab(key: Resource) {
    setResource(key);
    setCreating(false);
    setBase(undefined);
  }
  const locked = busy || pending !== null;
  const period = loaded?.periods.find((p) => p.id === periodId);
  const macroItems = loaded?.pages["macrocycle-plans"].items as
    Receipt<MacroArtifact>[] | undefined;
  const protocolItems = loaded?.pages["mesocycle-protocols"].items as
    Receipt<ProtocolArtifact>[] | undefined;
  const macroOptions =
    macroItems?.filter((item) =>
      item.artifact.sources.mesocycles.some((p) => p.period_id === periodId),
    ) ?? [];
  const protocolOptions =
    protocolItems?.filter(
      (item) => item.artifact.proposal.mesocycle_period_id === periodId,
    ) ?? [];
  const macro = macroOptions.find(
    (item) => item.artifact.artifact_id === macroId,
  );
  const protocol = protocolOptions.find(
    (item) => item.artifact.artifact_id === protocolId,
  );
  const selectedReceipt = loaded?.pages[resource].items.find(
    (item) => item.artifact.artifact_id === selected[resource],
  );

  const cyclePeriods =
    cycleContext?.boundary_revisions.at(-1)?.artifact.periods ??
    cycleContext?.program.artifact.periods ??
    [];
  const cyclePeriod = cyclePeriods.find((p) => p.id === periodId);
  const relevantEvents = cyclePeriod
    ? (
        cycleContext?.competition_revisions.at(-1)?.artifact.proposal
          .competitions ??
        cycleContext?.program.artifact.proposal.competitions ??
        []
      ).filter(
        (c) =>
          c.status === "planned" &&
          c.start_date <= cyclePeriod.end_date &&
          c.end_date >= cyclePeriod.start_date,
      )
    : [];
  const suggestedCapabilities = [
    ...new Set(relevantEvents.flatMap((c) => c.profile?.capability_keys ?? [])),
  ];
  return (
    <div className="space-y-7">
      {cycleError && <Message error>{cycleError}</Message>}
      {cyclePeriod && (
        <Card title="A felkészülés versenykövetelményei">
          <Competitions value={relevantEvents} />
          <p className="mt-4 text-sm text-zinc-400">
            A verseny követelményprofilja támpont a képességek kiválasztásához.
            A sportoló kiinduló állapota és személyes adatai alapján minden
            mezociklus szerepét külön kell megadni; a kimaradó képesség nem
            engedélyezett leépülés.
          </p>
          {!!cycleContext?.boundary_revisions.length && (
            <p className="mt-3 text-sm text-amber-100">
              A ciklushatárok módosultak. Ellenőrizd a terhelést, a
              képességszerepeket és a mérési időablakokat. A korábban rögzített
              protokollok az eredeti időablakaikkal maradnak meg.
            </p>
          )}
        </Card>
      )}
      <p className="rounded-xl border border-zinc-700 bg-zinc-900 p-4 text-sm leading-6 text-zinc-300">
        A célok a makrociklusból kapnak szerepet. A mérési protokoll előre
        rögzíti az összehasonlítás feltételeit; az értékelés jelzi a hiányzó
        adatot és a bizonytalanságot. Ez a munkafolyamat önmagában nem módosít
        edzéstervet.
      </p>
      <div ref={statusArea} tabIndex={-1} className="scroll-mt-5 outline-none">
        {(failure || pending || busy) && (
          <Message error={Boolean(failure)}>
            <div className="space-y-3">
              <p>
                {busy
                  ? "Mentés folyamatban…"
                  : failure || "Függő mentési kérés."}
              </p>
              {pending && (
                <>
                  <p>
                    {resourceLabels[pending.resource]} · a pontos eredeti kérést
                    megőriztük ebben a böngészőlapon. Bizonytalan kimenetelnél
                    ezt küldd újra; ne hozz létre új mérést helyette.
                  </p>
                  <div className="flex flex-wrap gap-3">
                    <button
                      className={secondaryClass}
                      type="button"
                      disabled={busy}
                      onClick={() => void send(pending)}
                    >
                      Ugyanaz a kérés újraküldése
                    </button>
                    {rejected && (
                      <button
                        className={secondaryClass}
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          sessionStorage.removeItem(PENDING_KEY);
                          setPending(null);
                          setFailure("");
                          setRejected(false);
                        }}
                      >
                        Vissza az űrlap szerkesztéséhez
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          </Message>
        )}
        {success && <Message>{success}</Message>}
      </div>
      {loadError && (
        <Message error>
          <p>{loadError}</p>
          <button
            type="button"
            className={secondaryClass + " mt-3"}
            onClick={() => setReload(reload + 1)}
          >
            Adatok újbóli betöltése
          </button>
        </Message>
      )}
      {!loaded && !loadError && (
        <p role="status" className="text-zinc-300">
          Képességek, ciklusok és mentett verziók betöltése…
        </p>
      )}
      {loaded && (
        <>
          <Card title="Ciklus kiválasztása">
            <Select
              label="Makro- vagy mezociklus"
              value={periodId}
              onChange={(event) => {
                const id = event.target.value;
                setPeriodId(id);
                setMacroId("");
                setProtocolId("");
                setBase(undefined);
                setCreating(false);
                setSelected({});
                const p = loaded.periods.find((p) => p.id === id);
                setResource(
                  p?.period_type === "MESOCYCLE"
                    ? "mesocycle-protocols"
                    : "macrocycle-plans",
                );
              }}
            >
              <option value="">
                Válassz ciklust · az előzmények ciklus nélkül is olvashatók
              </option>
              {loaded.periods
                .filter((p) =>
                  ["MACROCYCLE", "MESOCYCLE"].includes(p.period_type),
                )
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.period_type === "MACROCYCLE" ? "Makro" : "Mezo"} ·{" "}
                    {p.title} · {p.start_date} – {p.end_date}
                  </option>
                ))}
            </Select>
            {initialPeriod && !period && (
              <p className="mt-3 text-sm text-amber-200">
                A hivatkozott ciklus nem szerepel az elérhető ciklusok között.
              </p>
            )}
          </Card>
          <nav
            aria-label="Célkezelés munkafolyamata"
            className="flex flex-wrap gap-2"
          >
            {RESOURCES.map((key, index) => (
              <button
                key={key}
                type="button"
                onClick={() => changeTab(key)}
                aria-current={resource === key ? "page" : undefined}
                className={resource === key ? buttonClass : secondaryClass}
              >
                {index + 1}. {resourceLabels[key]}
              </button>
            ))}
          </nav>
          <Card title="Mentett előzmények · minden ciklus">
            <p className="mb-4 text-sm text-zinc-400">
              Válassz pontos verziót. A betöltés sorrendje nem választ ki
              automatikusan aktuális szülőverziót.
            </p>
            {!loaded.pages[resource].items.length ? (
              <p className="text-sm text-zinc-300">
                Még nincs ilyen mentett bejegyzés.
              </p>
            ) : (
              <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
                {loaded.pages[resource].items.map((item) => (
                  <button
                    type="button"
                    key={item.artifact.artifact_id}
                    onClick={() => {
                      setSelected((previous) => ({
                        ...previous,
                        [resource]: item.artifact.artifact_id,
                      }));
                      setCreating(false);
                    }}
                    className={`block w-full rounded-lg border p-3 text-left text-sm transition hover:border-teal-300 ${selected[resource] === item.artifact.artifact_id ? "border-teal-300 bg-teal-950/40" : "border-zinc-700 bg-zinc-950"}`}
                  >
                    <span className="block">{savedLabel(item)}</span>
                    <span className="mt-1 block break-all text-xs text-zinc-400">
                      {item.artifact.artifact_id.slice(0, 35)}…
                    </span>
                  </button>
                ))}
              </div>
            )}
            {loaded.pages[resource].has_more && (
              <button
                type="button"
                className={secondaryClass + " mt-4"}
                disabled={paging}
                onClick={() => void more()}
              >
                {paging ? "Betöltés…" : "További mentett verziók betöltése"}
              </button>
            )}
            {resource === "mesocycle-protocols" &&
              loaded.pages["macrocycle-plans"].has_more && (
                <p className="mt-4 text-sm text-zinc-400">
                  Ha a keresett szülőverzió még nem választható, a
                  Makrocikluscélok fülön töltsd be a további verziókat.
                </p>
              )}
            {(resource === "measurements" || resource === "assessments") &&
              loaded.pages["mesocycle-protocols"].has_more && (
                <p className="mt-4 text-sm text-zinc-400">
                  Ha a keresett protokoll még nem választható, a Mérési
                  protokollok fülön töltsd be a további verziókat.
                </p>
              )}
          </Card>
          {selectedReceipt && (
            <ArtifactDetails receipt={selectedReceipt} resource={resource} />
          )}
          {resource === "macrocycle-plans" &&
            period?.period_type === "MACROCYCLE" && (
              <>
                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    disabled={locked}
                    className={secondaryClass}
                    onClick={() => {
                      setBase(undefined);
                      setCreating(true);
                    }}
                  >
                    Új első makrociklus-verzió
                  </button>
                  {selectedReceipt &&
                    (selectedReceipt.artifact as MacroArtifact).proposal
                      .macrocycle_period_id === periodId &&
                    (selectedReceipt.artifact as MacroArtifact).proposal
                      .revision < 64 && (
                      <button
                        type="button"
                        disabled={locked}
                        className={secondaryClass}
                        onClick={() => {
                          setBase(selectedReceipt as Receipt<MacroArtifact>);
                          setCreating(true);
                        }}
                      >
                        Új verzió a kiválasztottból
                      </button>
                    )}
                </div>
                {creating && (
                  <MacroForm
                    key={periodId + (base?.artifact.artifact_id ?? "new")}
                    catalog={loaded.catalog}
                    suggestedCapabilities={suggestedCapabilities}
                    period={period}
                    periods={loaded.periods}
                    base={base as Receipt<MacroArtifact> | undefined}
                    locked={locked}
                    submit={submit}
                    invalid={report}
                  />
                )}
              </>
            )}
          {resource === "mesocycle-protocols" &&
            period?.period_type === "MESOCYCLE" && (
              <>
                <Card title="Pontos makrociklus-szülőverzió">
                  <Select
                    label="Makrociklusverzió ehhez a mezociklushoz"
                    value={macro?.artifact.artifact_id ?? ""}
                    disabled={locked}
                    onChange={(event) => {
                      setMacroId(event.target.value);
                      setCreating(false);
                      setBase(undefined);
                    }}
                  >
                    <option value="">
                      Válassz mentett makrociklus-verziót
                    </option>
                    {macroOptions.map((item) => (
                      <option
                        key={item.artifact.artifact_id}
                        value={item.artifact.artifact_id}
                      >
                        {savedLabel(item)} ·{" "}
                        {item.artifact.content_hash.slice(0, 8)}
                      </option>
                    ))}
                  </Select>
                </Card>
                {macro && (
                  <>
                    <div className="flex flex-wrap gap-3">
                      <button
                        type="button"
                        disabled={locked}
                        className={secondaryClass}
                        onClick={() => {
                          setBase(undefined);
                          setCreating(true);
                        }}
                      >
                        Új első mérési protokoll
                      </button>
                      {selectedReceipt &&
                        (selectedReceipt.artifact as ProtocolArtifact).proposal
                          .mesocycle_period_id === periodId &&
                        (selectedReceipt.artifact as ProtocolArtifact).proposal
                          .revision < 64 && (
                          <button
                            type="button"
                            disabled={locked}
                            className={secondaryClass}
                            onClick={() => {
                              setBase(
                                selectedReceipt as Receipt<ProtocolArtifact>,
                              );
                              setCreating(true);
                            }}
                          >
                            Új verzió a kiválasztott protokollból
                          </button>
                        )}
                    </div>
                    {creating && (
                      <ProtocolForm
                        key={
                          periodId +
                          macro.artifact.artifact_id +
                          (base?.artifact.artifact_id ?? "new")
                        }
                        catalog={loaded.catalog}
                        period={period}
                        macro={macro}
                        base={base as Receipt<ProtocolArtifact> | undefined}
                        locked={locked}
                        submit={submit}
                        invalid={report}
                      />
                    )}
                  </>
                )}
              </>
            )}
          {(resource === "measurements" || resource === "assessments") &&
            period?.period_type === "MESOCYCLE" && (
              <>
                <Card title="Pontos mérési protokoll">
                  <Select
                    label="Protokollverzió ehhez a mezociklushoz"
                    value={protocol?.artifact.artifact_id ?? ""}
                    disabled={locked}
                    onChange={(event) => {
                      setProtocolId(event.target.value);
                      setCreating(true);
                    }}
                  >
                    <option value="">Válassz mentett protokollverziót</option>
                    {protocolOptions.map((item) => (
                      <option
                        key={item.artifact.artifact_id}
                        value={item.artifact.artifact_id}
                      >
                        {savedLabel(item)} ·{" "}
                        {item.artifact.content_hash.slice(0, 8)}
                      </option>
                    ))}
                  </Select>
                </Card>
                {protocol && (
                  <>
                    {!creating ? (
                      <button
                        type="button"
                        className={secondaryClass}
                        disabled={locked}
                        onClick={() => setCreating(true)}
                      >
                        {resource === "measurements"
                          ? "Új mérési eredmény"
                          : "Új célértékelés"}
                      </button>
                    ) : resource === "measurements" ? (
                      <MeasurementForm
                        key={protocolId}
                        protocol={protocol}
                        catalog={loaded.catalog}
                        locked={locked}
                        submit={submit}
                        invalid={report}
                      />
                    ) : (
                      <AssessmentForm
                        key={protocolId}
                        protocol={protocol}
                        locked={locked}
                        submit={submit}
                        invalid={report}
                      />
                    )}
                  </>
                )}
              </>
            )}
          {!period && (
            <p className="text-sm leading-6 text-zinc-300">
              Új bejegyzéshez válassz ciklust. A makrocikluscélokat
              makrociklushoz, a protokollokat, méréseket és értékeléseket
              mezociklushoz lehet rögzíteni.
            </p>
          )}
          <div className="rounded-xl border border-zinc-700 p-4 text-sm leading-6 text-zinc-300">
            {!loaded.periods.some((p) => p.period_type === "MACROCYCLE") && (
              <p className="mb-3">
                Még nincs választható makrociklus. Először hozd létre a
                felkészülés ciklusait.
              </p>
            )}
            <Link
              href="/planning-cycles"
              className="text-teal-200 underline underline-offset-4"
            >
              Új felkészülés és ciklusok létrehozása
            </Link>
          </div>
          {period &&
            resource !== "macrocycle-plans" &&
            period.period_type === "MACROCYCLE" && (
              <p className="text-sm text-zinc-300">
                Ehhez a lépéshez válassz mezociklust.
              </p>
            )}
          {period &&
            resource === "macrocycle-plans" &&
            period.period_type === "MESOCYCLE" && (
              <p className="text-sm text-zinc-300">
                A képességek felosztásához válaszd ki a szülő makrociklust.
              </p>
            )}
        </>
      )}
    </div>
  );
}
