/** Bound the whole exchange, including a response body that never finishes.
 * Aborting this wait does not assert that a server-side import was cancelled.
 */
export async function withConnectionDeadline<T>(
  operation: (signal: AbortSignal) => Promise<T>,
  milliseconds: number,
  parent?: AbortSignal,
): Promise<T> {
  parent?.throwIfAborted();
  const controller = new AbortController();
  let rejectWait!: (reason: unknown) => void;
  const cancelled = new Promise<never>((_resolve, reject) => { rejectWait = reject; });
  const abort = (reason: unknown) => {
    controller.abort(reason);
    rejectWait(reason);
  };
  const onAbort = () => abort(parent?.reason ?? new DOMException("Request aborted", "AbortError"));
  parent?.addEventListener("abort", onAbort, { once: true });
  const timer = setTimeout(() => abort(new DOMException("Response deadline exceeded", "TimeoutError")), milliseconds);
  try {
    return await Promise.race([
      Promise.resolve().then(() => {
        controller.signal.throwIfAborted();
        return operation(controller.signal);
      }),
      cancelled,
    ]);
  } finally {
    clearTimeout(timer);
    parent?.removeEventListener("abort", onAbort);
  }
}
