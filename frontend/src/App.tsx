import { useCallback, useEffect, useRef, useState } from 'react';
import type { DetectError, DetectResponse } from './types/detection';
import type { ValidationSuccess } from './lib/validateImage';
import { MOCK_MODE, detect, toDetectError } from './api/client';
import { MOCK_SCENARIOS, type MockScenario } from './mocks/fixtures';
import { VERDICT_STYLE } from './lib/verdict';
import { UploadPanel } from './components/UploadPanel';
import { ImagePreview } from './components/ImagePreview';
import { QualityWarnings } from './components/QualityWarnings';
import { ResultCard } from './components/ResultCard';
import { SignalList } from './components/SignalList';
import { HeatmapViewer } from './components/HeatmapViewer';
import { VersionInfo } from './components/VersionInfo';
import { PrivacyNotice } from './components/PrivacyNotice';
import { EmptyState } from './components/EmptyState';
import { ErrorState } from './components/ErrorState';

type Status = 'idle' | 'loading' | 'done' | 'error';

export default function App() {
  const [status, setStatus] = useState<Status>('idle');
  const [file, setFile] = useState<File | null>(null);
  const [meta, setMeta] = useState<ValidationSuccess | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [result, setResult] = useState<DetectResponse | null>(null);
  const [error, setError] = useState<DetectError | null>(null);
  const [scenario, setScenario] = useState<MockScenario>('uncertain');
  const [announcement, setAnnouncement] = useState('');

  const verdictHeadingRef = useRef<HTMLHeadingElement>(null);
  const errorHeadingRef = useRef<HTMLHeadingElement>(null);
  const inFlight = useRef<AbortController | null>(null);
  const previewRef = useRef<string | null>(null);

  // Object URLs are revoked on replacement and on unmount.
  useEffect(() => {
    previewRef.current = previewUrl;
  }, [previewUrl]);
  useEffect(
    () => () => {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
      inFlight.current?.abort();
    },
    [],
  );

  const replacePreview = useCallback((next: string | null) => {
    setPreviewUrl((current) => {
      if (current && current !== next) URL.revokeObjectURL(current);
      return next;
    });
  }, []);

  // §10 — focus moves to the result (or error) heading once it exists.
  useEffect(() => {
    if (status === 'done' && result) {
      verdictHeadingRef.current?.focus();
      setAnnouncement(
        `${VERDICT_STYLE[result.verdict].announce} Estimated manipulation probability: ${result.fake_probability.toFixed(
          2,
        )}. Confidence: ${result.confidence_level}. The image should be manually reviewed.`,
      );
    }
    if (status === 'error' && error) {
      errorHeadingRef.current?.focus();
      setAnnouncement(`Detection failed. ${error.message}`);
    }
  }, [error, result, status]);

  const runDetection = useCallback(
    async (target: File, mockScenario: MockScenario) => {
      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;

      setStatus('loading');
      setError(null);
      setResult(null);
      setAnnouncement('Analysing capture.');

      try {
        const response = await detect(target, {
          scenario: mockScenario,
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setResult(response);
        setStatus('done');
      } catch (caught) {
        if (controller.signal.aborted) return;
        setError(toDetectError(caught));
        setStatus('error');
      } finally {
        if (inFlight.current === controller) inFlight.current = null;
      }
    },
    [],
  );

  const onSelect = useCallback(
    (selected: File, validation: ValidationSuccess) => {
      setFile(selected);
      setMeta(validation);
      void runDetection(selected, scenario);
    },
    [runDetection, scenario],
  );

  const onValidationError = useCallback(
    (message: string) => {
      setFile(null);
      setMeta(null);
      replacePreview(null);
      setResult(null);
      setError({ kind: 'validation', message });
      setStatus('error');
    },
    [replacePreview],
  );

  const onClear = useCallback(() => {
    inFlight.current?.abort();
    setFile(null);
    setMeta(null);
    replacePreview(null);
    setResult(null);
    setError(null);
    setStatus('idle');
    setAnnouncement('Capture cleared.');
  }, [replacePreview]);

  const onRetry = useCallback(() => {
    if (file) void runDetection(file, scenario);
    else setStatus('idle');
  }, [file, runDetection, scenario]);

  const busy = status === 'loading';

  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <a href="#result-column" className="sr-only-focusable btn-secondary absolute left-4 top-4 z-50">
        Skip to results
      </a>

      <Header
        scenario={scenario}
        onScenarioChange={(next) => {
          setScenario(next);
          if (file) void runDetection(file, next);
        }}
        busy={busy}
      />

      {/* Single polite live region for verdict and error announcements. */}
      <p aria-live="polite" role="status" className="sr-only">
        {announcement}
      </p>

      <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 pb-10 pt-6 sm:px-6">
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,40fr)_minmax(0,60fr)]">
          {/* Left column: upload → preview → quality. */}
          <div className="flex flex-col gap-5">
            <UploadPanel
              onSelect={onSelect}
              onPreview={replacePreview}
              onError={onValidationError}
              busy={busy}
            />

            {previewUrl ? (
              <ImagePreview
                previewUrl={previewUrl}
                meta={meta}
                filename={file?.name ?? 'capture'}
                onClear={onClear}
                disabled={busy}
              />
            ) : null}

            {result ? (
              <QualityWarnings quality={result.quality} verdict={result.verdict} />
            ) : null}
          </div>

          {/* Right column: verdict → signals → heatmap → versions. */}
          <div id="result-column" className="flex flex-col gap-5">
            {status === 'error' && error ? (
              <ErrorState error={error} onRetry={file ? onRetry : undefined} headingRef={errorHeadingRef} />
            ) : null}

            {status === 'idle' || status === 'loading' ? <EmptyState loading={busy} /> : null}

            {status === 'done' && result ? (
              <>
                <ResultCard
                  verdict={result.verdict}
                  probability={result.fake_probability}
                  confidence={result.confidence_level}
                  signals={result.signals}
                  result={result}
                  headingRef={verdictHeadingRef}
                />
                <SignalList signals={result.signals} />
                <HeatmapViewer
                  image={previewUrl}
                  map={result.heatmap_base64}
                  regionScores={result.region_scores}
                  requestId={result.request_id}
                  modelVersion={result.model_version}
                />
                <VersionInfo
                  model={result.model_version}
                  threshold={result.threshold_version}
                  calibration={result.calibration_version}
                  info={result.model_info}
                />
              </>
            ) : null}
          </div>
        </div>
      </main>

      <PrivacyNotice />
    </div>
  );
}

function Header({
  scenario,
  onScenarioChange,
  busy,
}: {
  scenario: MockScenario;
  onScenarioChange: (next: MockScenario) => void;
  busy: boolean;
}) {
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3 px-4 py-3.5 sm:px-6">
        <div className="flex items-center gap-3">
          <span
            aria-hidden="true"
            className="inline-flex h-8 w-8 items-center justify-center rounded-[9px] bg-blue-500 font-mono text-[15px] font-semibold text-surface"
          >
            F
          </span>
          <div>
            <h1 className="text-[16px] font-semibold leading-tight text-ink">Farebi</h1>
            <p className="text-micro text-ink-3">Image manipulation review console</p>
          </div>
        </div>

        {MOCK_MODE ? (
          <div className="flex items-center gap-2">
            <span className="rounded-[6px] border border-ochre-500 bg-ochre-50 px-2 py-0.5 text-micro font-medium text-ochre-700">
              Mock mode — fixture data, not model output
            </span>
            <label htmlFor="scenario" className="sr-only">
              Fixture scenario
            </label>
            <select
              id="scenario"
              value={scenario}
              disabled={busy}
              onChange={(event) => onScenarioChange(event.target.value as MockScenario)}
              className="anim rounded-[8px] border border-line-strong bg-surface px-2.5 py-1.5 text-[13px] text-ink"
            >
              {MOCK_SCENARIOS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        ) : null}
      </div>
    </header>
  );
}
