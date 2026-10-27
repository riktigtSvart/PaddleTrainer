"use client";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import Icon from "./icon";
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
  const [revision, setRevision] = useState(0),
    [pastDays, setPastDays] = useState(35);
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
      setNotice(receipt.run.state === "succeeded" ? "A frissítés befejeződött. Az átvett adatok elérhetők." : "");
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
  async function start(provider: Provider) {
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
          datasets: provider.allowed_datasets,
          past_days: pastDays,
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
        ? "Kapcsolat ellenőrzendő" : "Frissítés ellenőrzendő"
      : visible.some(p => continuationOnly(p.last_run)) ? "Átvétel folytatható" : "";
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
        <Icon name="refresh" className={busy ? "pt-spinning" : undefined} />
        <span className="pt-connection-badge">
          <Icon
            name={
              warning
                ? "alert"
                : busy || visible.some(p => continuationOnly(p.last_run))
                  ? "clock"
                  : visible.some(hasSuccessfulTransfer)
                    ? "check"
                    : "clock"
            }
          />
        </span>
        {short && <span className="pt-connection-warning">{short}</span>}
      </button>
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
                        provider.last_run?.state === "running" || continuationOnly(provider.last_run)
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
                    <dd>
                      {lastRunTime(provider, data.timezone_name)}
                    </dd>
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
                {provider.last_run && provider.last_run.state !== "running" && runMessages(provider.last_run).map(line => (
                  <p key={line} className="pt-notice" role={attention(provider) ? "status" : undefined}>{line}</p>
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
                      onClick={() => void start(provider)}
                    >
                      <Icon name="refresh" />
                      {busy ? "Folyamatban…" : "Szinkronizálás"}
                    </button>
                    <details className="pt-sync-options">
                      <summary>Átvett adatok és időszak</summary>
                      <p>
                        {provider.allowed_datasets
                          .map((d) => datasetLabels[d])
                          .join(", ") || "Nincs engedélyezett adatfajta."}{" "}
                        {provider.allowed_datasets.includes("session_details")
                          ? "· A hiányzó részleteket a legutóbbi napoktól, több lépésben vesszük át. A hátralévő mennyiséget az eredmény mutatja."
                          : "· alapadatok"}
                      </p>
                      <label>
                        Visszamenőleges időszak
                        <select
                          aria-label="Visszamenőleges időszak"
                          disabled={busy}
                          value={pastDays}
                          onChange={(e) => setPastDays(Number(e.target.value))}
                        >
                          <option value={7}>7 nap</option>
                          <option value={35}>35 nap</option>
                          <option value={89}>89 nap</option>
                        </select>
                      </label>
                      <p>
                        Az időszak a mai napot is tartalmazza; az edzéstervekhez
                        a következő 30 nap is bekerül.
                      </p>
                      <p>
                        A frissítés az edzéseket, az engedélyezett részletes
                        adatokat és a terveket veszi át. Az alvás, aktivitás és további állapotadatok a
                        profil Előzmények lapján kezelhetők.
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
                      {displayTime(provider.last_success_at, data.timezone_name)}
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
                            <span className="pt-sync-detail" key={line}>{line}</span>
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
