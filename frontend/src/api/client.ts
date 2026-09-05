/**
 * Typed fetch wrapper for `POST /v1/detect`.
 *
 * Design notes:
 *  - Relative URLs by default. `VITE_API_BASE` is empty in dev so the browser
 *    calls same-origin and Vite proxies to FastAPI. That keeps the app working
 *    behind a remote preview host, where `localhost` is the user's machine.
 *  - Every failure is normalised into a `DetectError` whose `message` is
 *    already the exact string frebi.md §9 requires, so components never build
 *    error copy themselves.
 */

import type { DetectError, DetectResponse } from '../types/detection';
import { API_ERROR } from '../lib/copy';
import { resolveFixture, type MockScenario } from '../mocks/fixtures';

export const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/+$/, '');
export const MOCK_MODE = import.meta.env.VITE_MOCK_API === 'true';
export const REQUEST_TIMEOUT_MS = Number.parseInt(
  import.meta.env.VITE_REQUEST_TIMEOUT_MS ?? '',
  10,
) || 30_000;

/** Thrown by the client; carries the already-resolved UI message. */
export class DetectRequestError extends Error {
  readonly detail: DetectError;

  constructor(detail: DetectError) {
    super(detail.message);
    this.name = 'DetectRequestError';
    this.detail = detail;
  }
}

interface ProblemBody {
  detail?: unknown;
  message?: unknown;
}

/** FastAPI puts the human message in `detail`; it may be a string or a list. */
function extractDetail(body: unknown): string | null {
  if (typeof body === 'string' && body.trim()) return body.trim();
  if (!body || typeof body !== 'object') return null;

  const problem = body as ProblemBody;
  const { detail } = problem;

  if (typeof detail === 'string' && detail.trim()) return detail.trim();

  if (Array.isArray(detail)) {
    const parts = detail
      .map((entry) => {
        if (typeof entry === 'string') return entry;
        if (entry && typeof entry === 'object' && 'msg' in entry) {
          return String((entry as { msg: unknown }).msg);
        }
        return null;
      })
      .filter((part): part is string => Boolean(part));
    if (parts.length) return parts.join(' ');
  }

  if (typeof problem.message === 'string' && problem.message.trim()) {
    return problem.message.trim();
  }
  return null;
}

async function readBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') ?? '';
  try {
    if (contentType.includes('application/json')) return await response.json();
    const text = await response.text();
    return text || null;
  } catch {
    return null;
  }
}

export interface DetectOptions {
  /** Only consulted when `MOCK_MODE` is on. */
  scenario?: MockScenario;
  /** Lets the caller cancel (e.g. the reviewer picks a different file). */
  signal?: AbortSignal;
}

const MOCK_LATENCY_MS = 700;

/**
 * Uploads one image and returns the detection result.
 * Rejects with `DetectRequestError` for every failure path.
 */
export async function detect(file: File, options: DetectOptions = {}): Promise<DetectResponse> {
  if (MOCK_MODE) return mockDetect(options);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException('timeout', 'TimeoutError')), REQUEST_TIMEOUT_MS);

  const onExternalAbort = () => controller.abort(new DOMException('cancelled', 'AbortError'));
  options.signal?.addEventListener('abort', onExternalAbort, { once: true });

  const body = new FormData();
  body.append('file', file, file.name || 'capture');

  try {
    const response = await fetch(`${API_BASE}/v1/detect`, {
      method: 'POST',
      body,
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });

    const payload = await readBody(response);

    if (!response.ok) {
      // §9.2 — 400 shows the server's own detail, 500 shows the fixed string.
      if (response.status >= 400 && response.status < 500) {
        throw new DetectRequestError({
          kind: 'http_400',
          status: response.status,
          message: extractDetail(payload) ?? API_ERROR.server,
        });
      }
      throw new DetectRequestError({
        kind: 'http_500',
        status: response.status,
        message: API_ERROR.server,
      });
    }

    if (!payload || typeof payload !== 'object') {
      throw new DetectRequestError({ kind: 'http_500', message: API_ERROR.server });
    }

    return payload as DetectResponse;
  } catch (error) {
    if (error instanceof DetectRequestError) throw error;

    if (error instanceof DOMException && error.name === 'AbortError') {
      // Distinguish "we gave up" from "the reviewer moved on".
      if (options.signal?.aborted) throw error;
      throw new DetectRequestError({ kind: 'timeout', message: API_ERROR.timeout });
    }
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new DetectRequestError({ kind: 'timeout', message: API_ERROR.timeout });
    }
    throw new DetectRequestError({ kind: 'network', message: API_ERROR.network });
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', onExternalAbort);
  }
}

async function mockDetect(options: DetectOptions): Promise<DetectResponse> {
  const scenario = options.scenario ?? 'uncertain';

  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, MOCK_LATENCY_MS);
    options.signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(new DOMException('cancelled', 'AbortError'));
      },
      { once: true },
    );
  });

  const outcome = resolveFixture(scenario);
  if ('error' in outcome) throw new DetectRequestError(outcome.error);
  return outcome.response;
}

/** Normalises anything thrown by `detect` into a renderable error. */
export function toDetectError(error: unknown): DetectError {
  if (error instanceof DetectRequestError) return error.detail;
  if (error instanceof DOMException && error.name === 'AbortError') {
    return { kind: 'network', message: API_ERROR.network };
  }
  return { kind: 'http_500', message: API_ERROR.server };
}
