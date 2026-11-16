/** One bounded retry for calendar reads. Parsing and proof checks stay with the caller. */
export const calendarTransportMessages: Record<string, string> = {
  CALENDAR_API_UNAVAILABLE:
    "A naptár kiszolgálója most nem érhető el. A Frissítés gombbal újrapróbálható.",
  CALENDAR_API_TIMEOUT:
    "A naptár betöltése túl sokáig tartott. A Frissítés gombbal újrapróbálható.",
  CALENDAR_API_RESPONSE_INVALID:
    "A naptár kiszolgálója nem értelmezhető választ adott.",
  CALENDAR_API_CONFIGURATION_INVALID:
    "A naptár kiszolgálókapcsolata nincs megfelelően beállítva.",
  CALENDAR_REQUEST_CANCELLED: "A naptári kérés megszakadt.",
};

async function transient(response: Response) {
  if (![502, 503, 504].includes(response.status)) return false;
  try {
    const value = await response.clone().json();
    return ["CALENDAR_API_UNAVAILABLE", "CALENDAR_API_TIMEOUT", "CALENDAR_SOURCE_UNAVAILABLE"].includes(value?.detail?.code);
  } catch {
    return false;
  }
}

function retryDelay(signal?: AbortSignal) {
  signal?.throwIfAborted();
  return new Promise<void>((resolve, reject) => {
    const cancel = () => {
      clearTimeout(timer);
      reject(signal?.reason);
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", cancel);
      resolve();
    }, 350);
    signal?.addEventListener("abort", cancel, { once: true });
  });
}

export async function calendarRead(url: string, signal?: AbortSignal, send: typeof fetch = fetch): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    signal?.throwIfAborted();
    let response: Response;
    try {
      response = await send(url, { signal, cache: "no-store", headers: { Accept: "application/json" } });
    } catch (error) {
      signal?.throwIfAborted();
      if (!(error instanceof TypeError)) throw error;
      if (attempt > 0) throw new Error(calendarTransportMessages.CALENDAR_API_UNAVAILABLE, { cause: error });
      await retryDelay(signal);
      continue;
    }
    if (attempt > 0 || !(await transient(response))) return response;
    await retryDelay(signal);
  }
}
