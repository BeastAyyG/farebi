import { useEffect, useMemo, useState } from 'react';
import type { HeatmapView, RegionScore } from '../types/detection';
import { HEATMAP_LIMITATION, PER_RESULT_WARNING, formatProbability } from '../lib/copy';
import { DIRECTION_STYLE, clamp01 } from '../lib/verdict';
import { base64ToBytes, downloadBytes, withPngTextMetadata } from '../lib/png';
import { Tabs, type TabItem } from './ui/Tabs';
import { DownloadIcon } from './ui/Icon';

export interface HeatmapViewerProps {
  /** Object URL of the uploaded capture, for the `original` and `overlay` views. */
  image: string | null;
  /** Bare base64 PNG attribution map, or null when unavailable. */
  map: string | null;
  /** Initial view. */
  mode?: HeatmapView;
  regionScores?: RegionScore[];
  requestId: string;
  modelVersion: string;
}

const VIEW_DESCRIPTION: Record<HeatmapView, string> = {
  original: 'the uploaded capture with no attribution applied',
  attribution:
    'the attribution map alone, where warm areas contributed toward a fake estimate and cool areas toward a real estimate',
  overlay: 'the uploaded capture with the attribution map drawn semi-transparently on top',
  region_scores: 'a per-region breakdown of attribution scores across the face',
};

/**
 * §4 — toggleable attribution views with the mandatory limitation notice, and
 * a download that carries that notice inside the PNG's own metadata so the
 * caveat cannot be separated from the picture.
 */
export function HeatmapViewer({
  image,
  map,
  mode = 'overlay',
  regionScores,
  requestId,
  modelVersion,
}: HeatmapViewerProps) {
  // Choose an opening view that can actually render. `mode` is honoured when
  // its inputs are present, otherwise we fall back in order of usefulness.
  const [view, setView] = useState<HeatmapView>(() => {
    const canShow: Record<HeatmapView, boolean> = {
      original: Boolean(image),
      attribution: Boolean(map),
      overlay: Boolean(image && map),
      region_scores: Boolean(regionScores && regionScores.length > 0),
    };
    if (canShow[mode]) return mode;
    return (
      (['overlay', 'attribution', 'original', 'region_scores'] as HeatmapView[]).find(
        (candidate) => canShow[candidate],
      ) ?? 'original'
    );
  });
  const [overlayOpacity, setOverlayOpacity] = useState(0.6);

  const mapSrc = map ? `data:image/png;base64,${map}` : null;
  const hasRegions = Boolean(regionScores && regionScores.length > 0);

  const tabs: TabItem<HeatmapView>[] = useMemo(
    () => [
      { id: 'original', label: 'Original', glyph: '▣', disabled: !image, disabledReason: 'No capture preview available' },
      {
        id: 'attribution',
        label: 'Attribution',
        glyph: '◍',
        disabled: !mapSrc,
        disabledReason: 'No attribution map was returned for this capture',
      },
      {
        id: 'overlay',
        label: 'Overlay',
        glyph: '◫',
        disabled: !mapSrc || !image,
        disabledReason: 'Overlay needs both a capture preview and an attribution map',
      },
      {
        id: 'region_scores',
        label: 'Region scores',
        glyph: '▤',
        disabled: !hasRegions,
        disabledReason: 'No per-region scores were returned for this capture',
      },
    ],
    [hasRegions, image, mapSrc],
  );

  // A capture may arrive without a preview, without a map, or without regions.
  // Never leave the viewer parked on a tab that cannot render anything.
  useEffect(() => {
    const current = tabs.find((tab) => tab.id === view);
    if (current && !current.disabled) return;
    const firstEnabled = tabs.find((tab) => !tab.disabled);
    if (firstEnabled) setView(firstEnabled.id);
  }, [tabs, view]);

  const allDisabled = tabs.every((tab) => tab.disabled);

  function onDownload() {
    if (!map) return;
    const bytes = withPngTextMetadata(base64ToBytes(map), {
      Title: 'Farebi attribution heatmap',
      Description: HEATMAP_LIMITATION,
      Warning: PER_RESULT_WARNING,
      Software: `Farebi ${modelVersion}`,
      Comment: `request_id ${requestId}`,
      Disclaimer:
        'Not definitive proof of manipulation. Combine with manual review and capture/liveness controls.',
    });
    downloadBytes(bytes, `farebi-heatmap-${requestId.slice(0, 8)}.png`);
  }

  return (
    <section aria-labelledby="heatmap-heading" className="card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="heatmap-heading" className="text-[15px] font-semibold text-ink">
          Attribution heatmap
        </h2>
        <button
          type="button"
          className="btn-secondary"
          onClick={onDownload}
          disabled={!map}
          title={
            map
              ? 'Download the attribution map as PNG, with the limitation notice embedded in its metadata'
              : 'No attribution map available to download'
          }
        >
          <DownloadIcon />
          Download PNG
        </button>
      </div>

      <div className="mt-3">
        {allDisabled ? (
          <div className="flex min-h-[160px] items-center justify-center rounded-[10px] border border-line bg-sunken p-6">
            <p className="text-center text-note text-ink-3">
              No attribution map was returned for this capture, so there is nothing to visualise.
            </p>
          </div>
        ) : (
          <Tabs items={tabs} value={view} onChange={setView} label="Heatmap view">
            <div
              className="flex min-h-[220px] items-center justify-center rounded-[10px] border border-line bg-sunken p-3"
              aria-live="polite"
            >
            {view === 'region_scores' ? (
              <RegionScoreTable scores={regionScores ?? []} />
            ) : (
              <figure className="m-0 flex flex-col items-center gap-2">
                <div className="relative">
                  {view !== 'attribution' && image ? (
                    <img
                      src={image}
                      alt=""
                      aria-hidden="true"
                      className="max-h-[360px] max-w-full rounded-[8px] object-contain"
                    />
                  ) : null}

                  {view === 'attribution' && mapSrc ? (
                    <img
                      src={mapSrc}
                      alt={`Attribution heatmap, ${VIEW_DESCRIPTION.attribution}`}
                      aria-label={`Attribution heatmap showing ${VIEW_DESCRIPTION.attribution}`}
                      className="max-h-[360px] max-w-full rounded-[8px] object-contain"
                      style={{ imageRendering: 'auto' }}
                    />
                  ) : null}

                  {view === 'overlay' && mapSrc ? (
                    <img
                      src={mapSrc}
                      alt=""
                      aria-hidden="true"
                      className="pointer-events-none absolute inset-0 h-full w-full rounded-[8px] object-fill"
                      style={{ opacity: overlayOpacity, mixBlendMode: 'multiply' }}
                    />
                  ) : null}

                  {/* One accessible name per view, always describing the current mode. */}
                  {view !== 'attribution' ? (
                    <span className="sr-only" role="img" aria-label={`Heatmap view: ${VIEW_DESCRIPTION[view]}`} />
                  ) : null}

                  {!image && !mapSrc ? (
                    <p className="px-6 py-10 text-center text-note text-ink-3">
                      No attribution map was returned for this capture.
                    </p>
                  ) : null}
                </div>

                {view === 'overlay' && mapSrc && image ? (
                  <div className="mt-1 flex w-full max-w-xs items-center gap-2">
                    <label htmlFor="overlay-opacity" className="text-micro text-ink-3">
                      Overlay
                    </label>
                    <input
                      id="overlay-opacity"
                      type="range"
                      min={0.1}
                      max={1}
                      step={0.05}
                      value={overlayOpacity}
                      onChange={(event) => setOverlayOpacity(Number(event.target.value))}
                      aria-valuetext={`${Math.round(overlayOpacity * 100)} of 100`}
                      className="flex-1 accent-[var(--blue-500)]"
                    />
                    <span className="w-10 text-right font-mono text-micro text-ink-3">
                      {overlayOpacity.toFixed(2)}
                    </span>
                  </div>
                ) : null}
              </figure>
            )}
            </div>
          </Tabs>
        )}
      </div>

      {!allDisabled && view !== 'region_scores' ? <AttributionLegend /> : null}

      {/* §4.2 — mandatory, never behind a toggle. */}
      <p className="limitation mt-3">{HEATMAP_LIMITATION}</p>
    </section>
  );
}

function AttributionLegend() {
  return (
    <div className="mt-3">
      <div
        role="img"
        aria-label="Legend: the colour ramp runs from blue, meaning a contribution toward real, through neutral, to terracotta, meaning a contribution toward fake."
        className="h-2.5 w-full rounded-full border border-line bg-attribution"
      />
      <div className="mt-1 flex justify-between text-micro text-ink-3">
        <span className="flex items-center gap-1">
          <span aria-hidden="true" className="font-mono">
            ↓
          </span>
          toward real
        </span>
        <span>neutral</span>
        <span className="flex items-center gap-1">
          toward fake
          <span aria-hidden="true" className="font-mono">
            ↑
          </span>
        </span>
      </div>
    </div>
  );
}

function RegionScoreTable({ scores }: { scores: RegionScore[] }) {
  if (scores.length === 0) {
    return (
      <p className="px-6 py-10 text-center text-note text-ink-3">
        No per-region scores were returned for this capture.
      </p>
    );
  }

  return (
    <table className="w-full border-collapse text-note">
      <caption className="sr-only">
        Attribution score by facial region. Higher scores mean the region contributed more to the
        estimate.
      </caption>
      <thead>
        <tr className="text-left text-micro uppercase tracking-wide text-ink-3">
          <th scope="col" className="pb-2 font-semibold">
            Region
          </th>
          <th scope="col" className="pb-2 font-semibold">
            Contribution
          </th>
          <th scope="col" className="pb-2 text-right font-semibold">
            Score
          </th>
        </tr>
      </thead>
      <tbody>
        {scores.map((entry) => {
          const direction = DIRECTION_STYLE[entry.direction ?? 'neutral'] ?? DIRECTION_STYLE.neutral;
          const score = clamp01(entry.score);
          return (
            <tr key={entry.region} className="border-t border-line">
              <th scope="row" className="py-2 pr-3 text-left font-medium capitalize text-ink">
                {entry.region}
              </th>
              <td className="py-2 pr-3">
                <span className="flex items-center gap-2">
                  <span className="h-2 w-full max-w-[140px] overflow-hidden rounded-full bg-sunken">
                    <span
                      className={`block h-full rounded-full ${direction.fill}`}
                      style={{ width: `${score * 100}%` }}
                    />
                  </span>
                  <span className={`whitespace-nowrap text-micro ${direction.ink}`}>
                    <span aria-hidden="true" className="mr-1 font-mono">
                      {direction.arrow}
                    </span>
                    {direction.label}
                  </span>
                </span>
              </td>
              <td className="py-2 text-right font-mono text-ink-2">{formatProbability(score)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
