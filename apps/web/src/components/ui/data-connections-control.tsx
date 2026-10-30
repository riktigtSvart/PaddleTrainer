"use client";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import Icon from "./icon";
import {
  LOCAL_REFRESH_EVENT,
  localChoice,
  readChoice,
  preferenceKey,
  choiceProvider,
} from "@/lib/data-connections/preferences";
import type { RefreshChoice } from "@/lib/data-connections/preferences";
import {
  ConnectionError,
  errorText,
  findSync,
  loadStatus,
  resultCounts,
  resultDetails,
  runMessages,
  sendSync,
} from "@/lib/data-connections/client";
import {
  attention,
  connectionAttention,
  continuationOnly,
  datasetLabels,
  displayTime,
  hasSuccessfulTransfer,
  lastRunTime,
  PENDING_KEY,
  providerState,
  readBody,
  readPending,
  UPDATED_EVENT,
} from "@/lib/data-connections/contracts";
import type {
  Pending,
  Provider,
  Receipt,
  Status,
} from "@/lib/data-connections/contracts";

const message = (e: unknown) =>
  e instanceof Error ? e.message : "Az adatkapcsolat most nem olvasható.";

export default function DataConnectionsControl() {
  const [open, setOpen] = useState(false),
    [data, setData] = useState<Status | null>(null);
  const [pending, setPending] = useState<Pending | null>(null),
    [ready, setReady] = useState(false);
  const [sending, setSending] = useState(false),
    [storageBlocked, setStorageBlocked] = useState(false);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [retryAllowed, setRetryAllowed] = useState(false),
    [rejected, setRejected] = useState(false);
  const [revision, setRevision] = useState(0);
  const [choiceState, setChoiceState] = useState<{
    owner: string;
    value: RefreshChoice;
  } | null>(null);
  const restoredOwner = useRef<string | null>(null);
  const container = useRef<HTMLDivElement>(null),
    trigger = useRef<HTMLButtonElement>(null),
    closeButton = useRef<HTMLButtonElement>(null);
  const sendingRef = useRef(false),
    pendingRef = useRef<Pending | null>(null),
    announced = useRef(new Set<string>());
  const observed = useRef(new Map<string, string>());
  const panelId = useId();

  function announce(receipt: Receipt) {
    if (
      receipt.run.state !== "running" &&
      !announced.current.has(receipt.run.request_id)
    ) {
      announced.current.add(receipt.run.request_id);
      window.dispatchEvent(
        new CustomEvent(UPDATED_EVENT, {
          detail: {
            provider: receipt.run.provider,
            request_id: receipt.run.request_id,
          },
        }),
      );
    }
  }
  function resolve(receipt: Receipt, envelope: Pending) {
    announce(receipt);
    if (
      receipt.run.state === "running" ||
      pendingRef.current?.body !== envelope.body
    )
      return;
    try {
      sessionStorage.removeItem(PENDING_KEY);
      pendingRef.current = null;
      setPending(null);
      setRetryAllowed(false);
      setRejected(false);
      setNotice(
        receipt.run.state === "succeeded"
          ? "A frissítés befejeződött. Az átvett adatok elérhetők."
          : "",
      );
      setError("");
      setRevision((n) => n + 1);
    } catch {
      setStorageBlocked(true);
      setError(
        "A frissítés eredménye megvan, de a függő kérés a böngésző tárhelyéről nem törölhető.",
      );
    }
  }

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try {
        const saved = sessionStorage.getItem(PENDING_KEY);
        if (saved) {
          const value = readPending(saved);
          pendingRef.current = value;
          setPending(value);
        }
      } catch {
        setStorageBlocked(true);
        setError(
          "A böngészőben megőrzött frissítési kérés vagy a tárhely nem olvasható.",
        );
      }
      setReady(true);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!ready) return;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function check() {
      let running = !!pending;
      try {
        const status = await loadStatus(abort.signal);
        if (abort.signal.aborted) return;
        setData(status);
        if (restoredOwner.current !== status.athlete_id) {
          restoredOwner.current = status.athlete_id;
          let value: RefreshChoice = localChoice;
          try {
            const raw = localStorage.getItem(preferenceKey(status.athlete_id));
            if (raw) value = readChoice(raw, status.athlete_id);
          } catch {
            setNotice(
              "A korábbi frissítési beállítás nem olvasható; válaszd ki újra a műveletet.",
            );
          }
          setChoiceState({ owner: status.athlete_id, value });
        }
        for (const p of status.providers) {
          if (!p.last_run) continue;
          const current = p.last_run.request_id + ":" + p.last_run.state;
          const previous = observed.current.get(p.key);
          observed.current.set(p.key, current);
          if (
            previous &&
            previous !== current &&
            p.last_run.state !== "running" &&
            !announced.current.has(p.last_run.request_id)
          ) {
            announced.current.add(p.last_run.request_id);
            window.dispatchEvent(
              new CustomEvent(UPDATED_EVENT, {
                detail: { provider: p.key, request_id: p.last_run.request_id },
              }),
            );
          }
        }
        running ||= status.providers.some(
          (p) => p.last_run?.state === "running",
        );
        if (pending) {
          if (pending.owner !== status.athlete_id)
            throw new Error(
              "A függő frissítés másik sportolóhoz tartozik; az eredményét külön ellenőrizni kell.",
            );
          try {
            const found = await findSync(pending, abort.signal);
            if (abort.signal.aborted) return;
            setRetryAllowed(false);
            resolve(found, pending);
          } catch (e) {
            if (abort.signal.aborted) return;
            if (
              e instanceof ConnectionError &&
              e.code === "DATA_SYNC_REQUEST_NOT_FOUND"
            ) {
              if (!sendingRef.current) setRetryAllowed(true);
            } else throw e;
          }
        } else setError("");
      } catch (e) {
        if (!abort.signal.aborted) setError(message(e));
      }
      if (!abort.signal.aborted)
        timer = setTimeout(check, running ? 3000 : 60000);
    }
    void check();
    return () => {
      abort.abort();
      clearTimeout(timer);
    };
    // resolve only consumes a verified receipt and its frozen envelope; it holds no render state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, revision, pending]);

  useEffect(() => {
    if (!open) return;
    closeButton.current?.focus();
    function key(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    }
    function outside(e: PointerEvent) {
      if (e.target instanceof Node && !container.current?.contains(e.target))
        setOpen(false);
    }
    document.addEventListener("keydown", key);
    document.addEventListener("pointerdown", outside);
    return () => {
      document.removeEventListener("keydown", key);
      document.removeEventListener("pointerdown", outside);
    };
  }, [open]);

  async function submit(envelope: Pending) {
    if (sendingRef.current) return;
    sendingRef.current = true;
    setSending(true);
    setError("");
    setNotice("");
    setRetryAllowed(false);
    setRejected(false);
    try {
      resolve(await sendSync(envelope), envelope);
    } catch (e) {
      setError(
        message(e) + " Az eredményt ellenőrizzük; új kérés még nem indul.",
      );
      if (e instanceof ConnectionError && e.status >= 400 && e.status < 500)
        setRejected(true);
    } finally {
      sendingRef.current = false;
      setSending(false);
      setRevision((n) => n + 1);
    }
  }
  async function start(provider: Provider, chosen?: RefreshChoice) {
    if (
      !data ||
      !ready ||
      storageBlocked ||
      pendingRef.current ||
      sendingRef.current
    )
      return;
    try {
      const body = JSON.stringify(
        readBody({
          request_id: crypto.randomUUID(),
          provider: provider.key,
          datasets:
            chosen?.mode === "provider"
              ? chosen.datasets
              : provider.allowed_datasets,
          past_days: chosen?.mode === "provider" ? chosen.pastDays : 35,
          future_days: 30,
        }),
      );
      const envelope: Pending = {
        version: "data-sync-pending-v0.1",
        owner: data.athlete_id,
        body,
      };
      sessionStorage.setItem(PENDING_KEY, JSON.stringify(envelope));
      pendingRef.current = envelope;
      setPending(envelope);
      await submit(envelope);
    } catch (e) {
      setStorageBlocked(true);
      setError(
        "A megismételhető frissítési kérés nem őrizhető meg. " + message(e),
      );
    }
  }
  function discardRejected() {
    if (!retryAllowed || !rejected || sendingRef.current) return;
    try {
      sessionStorage.removeItem(PENDING_KEY);
      pendingRef.current = null;
      setPending(null);
      setRejected(false);
      setRetryAllowed(false);
      setError("");
      setRevision((n) => n + 1);
    } catch {
      setError("A függő kérés nem törölhető a böngésző tárhelyéről.");
    }
  }
  const choice =
    choiceState?.owner === data?.athlete_id
      ? (choiceState?.value ?? localChoice)
      : localChoice;
  function choose(value: RefreshChoice) {
    if (!data || busy) return;
    setChoiceState({ owner: data.athlete_id, value });
    try {
      localStorage.setItem(
        preferenceKey(data.athlete_id),
        JSON.stringify({ version: 1, owner: data.athlete_id, choice: value }),
      );
    } catch {
      setNotice(
        "Ez a frissítési beállítás csak a jelenlegi megnyitásban marad meg.",
      );
    }
  }
  function localRefresh() {
    window.dispatchEvent(new Event(LOCAL_REFRESH_EVENT));
    setRevision((n) => n + 1);
    setNotice(
      "A tárolt adatok újraolvasását kértük. Szolgáltatói adatátvétel nem indult.",
    );
  }
  async function repeat() {
    if (busy || !ready || storageBlocked) return;
    if (choice.mode === "local") {
      localRefresh();
      return;
    }
    const provider = data && choiceProvider(choice, data);
    if (!provider) {
      setOpen(true);
      setNotice(
        "A korábbi szolgáltatói művelet most nem indítható. Ellenőrizd a kapcsolatot és az engedélyezett adatokat.",
      );
      return;
    }
    await start(provider, choice);
  }
  const visible = data?.providers.filter((p) => p.implemented) ?? [];
  const busy =
    sending ||
    !!pending ||
    visible.some((p) => p.last_run?.state === "running");
  const warning = !!error || storageBlocked || visible.some(attention);
  const short = error
    ? "Állapot ellenőrzendő"
    : warning
      ? visible.some(connectionAttention)
        ? "Kapcsolat ellenőrzendő"
        : "Frissítés ellenőrzendő"
      : visible.some((p) => continuationOnly(p.last_run))
        ? "Átvétel folytatható"
        : "";
  const title = !data
    ? "Adatkapcsolatok · állapot betöltése"
    : visible
        .map(
          (p) =>
            `${p.label}: ${providerState(p)}. Legutóbbi frissítés vége: ${lastRunTime(p, data.timezone_name)}`,
        )
        .join("\n");

  return (
    <div className="pt-connections" ref={container}>
      <div className="pt-refresh-split">
        <button
          type="button"
          className="pt-button pt-refresh-main"
          disabled={
            !ready ||
            !data ||
            choiceState?.owner !== data.athlete_id ||
            busy ||
            storageBlocked
          }
          onClick={() => void repeat()}
          title={
            choice.mode === "local"
              ? "Tárolt adatok újraolvasása · nincs szolgáltatói szinkronizálás"
              : `${choice.provider} · legutóbb választott adatfajták és időszak`
          }
        >
          <Icon name="refresh" className={busy ? "pt-spinning" : undefined} />
          <span>{busy ? "Frissítés…" : "Frissítés"}</span>
        </button>
        <button
          type="button"
          className={`pt-button pt-connection-trigger${warning ? " needs-attention" : ""}`}
          ref={trigger}
          aria-label="Adatkapcsolatok"
          aria-expanded={open}
          aria-controls={panelId}
          aria-haspopup="dialog"
          title={title}
          onClick={() => {
            setOpen((x) => !x);
            setRevision((n) => n + 1);
          }}
        >
          <Icon name="right" />
          <span className="pt-connection-badge">
            <Icon
              name={
                warning
                  ? "alert"
                  : busy || visible.some((p) => continuationOnly(p.last_run))
                    ? "clock"
                    : visible.some(hasSuccessfulTransfer)
                      ? "check"
                      : "clock"
              }
            />
          </span>
          {short && <span className="pt-connection-warning">{short}</span>}
        </button>
      </div>
      <span className="pt-refresh-caption">
        {choice.mode === "local"
          ? "Tárolt adatok"
          : (data?.providers.find((p) => p.key === choice.provider)?.label ??
            choice.provider)}
      </span>
      <span className="pt-sr-only" role="status">
        {busy ? "Adatfrissítés vagy eredményellenőrzés folyamatban" : short}
      </span>
      {open && (
        <div
          className="pt-connection-panel pt-panel"
          id={panelId}
          role="dialog"
          aria-label="Adatkapcsolatok"
        >
          <div className="pt-connection-heading">
            <h2>Adatkapcsolatok</h2>
            <button
              type="button"
              className="pt-button pt-icon-button"
              aria-label="Adatkapcsolatok bezárása"
              ref={closeButton}
              onClick={() => {
                setOpen(false);
                trigger.current?.focus();
              }}
            >
              <Icon name="close" />
            </button>
          </div>
          {error && (
            <p className="pt-notice pt-connection-error" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="pt-notice" role="status">
              {notice}
            </p>
          )}
          {!data && (
            <p className="pt-notice">A tárolt kapcsolati állapot betöltése…</p>
          )}
          {data && (
            <fieldset className="pt-refresh-choice" disabled={busy}>
              <legend>A főgomb művelete</legend>
              <label>
                <input
                  type="radio"
                  name={panelId + "choice"}
                  checked={choice.mode === "local"}
                  onChange={() => choose(localChoice)}
                />
                Tárolt adatok újraolvasása
              </label>
              {visible.map((p) => (
                <label key={p.key}>
                  <input
                    type="radio"
                    name={panelId + "choice"}
                    checked={
                      choice.mode === "provider" && choice.provider === p.key
                    }
                    disabled={
                      p.connection_state !== "connected" ||
                      !p.manual_sync_supported ||
                      !p.allowed_datasets.length
                    }
                    onChange={() =>
                      choose({
                        mode: "provider",
                        provider: p.key,
                        pastDays: 35,
                        datasets: [...p.allowed_datasets],
                      })
                    }
                  />
                  {p.label} · adatok átvétele
                </label>
              ))}
              {choice.mode === "provider" && (
                <>
                  <label>
                    Visszamenőleges időszak
                    <select
                      value={choice.pastDays}
                      onChange={(e) =>
                        choose({
                          ...choice,
                          pastDays: Number(e.target.value) as 7 | 35 | 89,
                        })
                      }
                    >
                      <option value={7}>7 nap</option>
                      <option value={35}>35 nap</option>
                      <option value={89}>89 nap</option>
                    </select>
                  </label>
                  {data.providers
                    .find((p) => p.key === choice.provider)
                    ?.allowed_datasets.map((dataset) => (
                      <label key={dataset}>
                        <input
                          type="checkbox"
                          checked={choice.datasets.includes(dataset)}
                          disabled={
                            choice.datasets.length === 1 &&
                            choice.datasets.includes(dataset)
                          }
                          onChange={(e) =>
                            choose({
                              ...choice,
                              datasets: e.target.checked
                                ? [...choice.datasets, dataset]
                                : choice.datasets.filter((d) => d !== dataset),
                            })
                          }
                        />
                        {datasetLabels[dataset]}
                      </label>
                    ))}
                  <small>
                    Az edzéstervekhez a következő 30 napot is kérjük.
                  </small>
                </>
              )}
              <button
                type="button"
                className="pt-button pt-primary"
                disabled={busy || storageBlocked || !ready}
                onClick={() => void repeat()}
              >
                Kiválasztott művelet indítása
              </button>
              <small>
                A választás megjegyezhető; a kiválasztás önmagában nem indít
                adatátvételt.
              </small>
            </fieldset>
          )}
          {data &&
            visible.map((provider) => (
              <section className="pt-provider" key={provider.key}>
                <div className="pt-provider-title">
                  <h3>{provider.label}</h3>
                  <span
                    className={
                      attention(provider) ? "pt-provider-attention" : ""
                    }
                  >
                    <Icon
                      name={
                        provider.last_run?.state === "running" ||
                        continuationOnly(provider.last_run)
                          ? "clock"
                          : attention(provider)
                            ? "alert"
                            : hasSuccessfulTransfer(provider)
                              ? "check"
                              : "clock"
                      }
                    />
                    {providerState(provider)}
                  </span>
                </div>
                <dl>
                  <div>
                    <dt>Legutóbbi frissítés vége</dt>
                    <dd>{lastRunTime(provider, data.timezone_name)}</dd>
                  </div>
                  <div>
                    <dt>Legfrissebb átvett edzés</dt>
                    <dd>
                      {displayTime(
                        provider.latest_session_at,
                        data.timezone_name,
                      )}
                    </dd>
                  </div>
                </dl>
                {provider.last_run &&
                  provider.last_run.state !== "running" &&
                  runMessages(provider.last_run).map((line) => (
                    <p
                      key={line}
                      className="pt-notice"
                      role={attention(provider) ? "status" : undefined}
                    >
                      {line}
                    </p>
                  ))}
                {provider.connection_state === "connected" && (
                  <>
                    <button
                      type="button"
                      className="pt-button pt-primary"
                      aria-label={`${provider.label} szinkronizálása`}
                      disabled={
                        !provider.manual_sync_supported ||
                        provider.allowed_datasets.length === 0 ||
                        busy ||
                        storageBlocked ||
                        !ready
                      }
                      onClick={() => {
                        const selected: RefreshChoice =
                          choice.mode === "provider" &&
                          choice.provider === provider.key
                            ? choice
                            : {
                                mode: "provider",
                                provider: provider.key,
                                pastDays: 35,
                                datasets: [...provider.allowed_datasets],
                              };
                        choose(selected);
                        void start(provider, selected);
                      }}
                    >
                      <Icon name="refresh" />
                      {busy ? "Folyamatban…" : "Szinkronizálás"}
                    </button>
                    <details className="pt-sync-options">
                      <summary>Átvételi tudnivalók</summary>
                      <p>
                        A szolgáltatóhoz engedélyezett adatfajták:{" "}
                        {provider.allowed_datasets
                          .map((d) => datasetLabels[d])
                          .join(", ")}
                        . A főgomb műveletét, adatfajtáit és időszakát fent
                        választhatod ki.
                      </p>
                      <p>
                        A részletes edzésadatok átvétele több lépésben
                        folytatható. Alvás és aktivitás a Sportolói profil
                        Előzmények lapján kezelhető.
                      </p>
                    </details>
                  </>
                )}
                {provider.connection_state === "configuration_required" && (
                  <p className="pt-notice">
                    A Polar-kapcsolat szerveroldali beállítása szükséges.
                  </p>
                )}
                {provider.connection_state !== "configuration_required" &&
                  connectionAttention(provider) && (
                    <form
                      action="/api/data-connections/polar/connect"
                      method="get"
                    >
                      <button type="submit" className="pt-button">
                        {provider.connection_state === "not_connected"
                          ? "Polar-fiók összekapcsolása"
                          : "Polar-hozzáférés megújítása"}
                      </button>
                    </form>
                  )}
                {provider.last_run && provider.last_run.state !== "running" && (
                  <details className="pt-sync-options">
                    <summary>Legutóbbi frissítés részletei</summary>
                    <p className="pt-notice">
                      Utolsó kihagyás nélküli frissítés:{" "}
                      {displayTime(
                        provider.last_success_at,
                        data.timezone_name,
                      )}
                      {provider.last_success_datasets.length > 0 &&
                        ` · ${provider.last_success_datasets.map((d) => datasetLabels[d]).join(", ")}`}
                    </p>
                    {provider.last_run.error_code && (
                      <p className="pt-notice">
                        {errorText(provider.last_run.error_code)}
                      </p>
                    )}
                    {provider.last_run.datasets.map((d) => (
                      <div className="pt-sync-result" key={d.dataset}>
                        <strong>{datasetLabels[d.dataset]}</strong>
                        <span>
                          {resultCounts(d)}
                          {resultDetails(d).map((line) => (
                            <span className="pt-sync-detail" key={line}>
                              {line}
                            </span>
                          ))}
                          {d.error_code && (
                            <>
                              <br />
                              {errorText(d.error_code)}
                            </>
                          )}
                        </span>
                      </div>
                    ))}
                  </details>
                )}
              </section>
            ))}
          {pending && (
            <div className="pt-notice" role="status">
              Egy korábbi kérés eredményét ellenőrizzük.{" "}
              {retryAllowed && (
                <button
                  type="button"
                  className="pt-button"
                  disabled={
                    sending ||
                    storageBlocked ||
                    pending.owner !== data?.athlete_id
                  }
                  onClick={() => void submit(pending)}
                >
                  Ugyanaz a kérés újraküldése
                </button>
              )}
              {rejected && retryAllowed && (
                <button
                  type="button"
                  className="pt-button"
                  disabled={sending}
                  onClick={discardRejected}
                >
                  Elutasított kérés elvetése
                </button>
              )}
            </div>
          )}
          <button
            type="button"
            className="pt-button pt-local-check"
            onClick={localRefresh}
          >
            Tárolt adatok újraolvasása
          </button>
          <button
            type="button"
            className="pt-button pt-local-check"
            onClick={() => setRevision((n) => n + 1)}
          >
            Kapcsolati állapot újraolvasása
          </button>
          <details className="pt-sync-options">
            <summary>További szolgáltatók</summary>
            {data?.providers
              .filter((p) => !p.implemented)
              .map((p) => (
                <p key={p.key}>
                  {p.label} · {providerState(p)}
                </p>
              ))}
            <p>A kapcsolatok szolgáltatónként külön hozzáférést igényelnek.</p>
          </details>
          <Link
            href="/settings#data-connections"
            onClick={() => setOpen(false)}
          >
            Kapcsolatok beállításai
          </Link>
        </div>
      )}
    </div>
  );
}
