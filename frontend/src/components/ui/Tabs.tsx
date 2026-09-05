import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';

export interface TabItem<T extends string> {
  id: T;
  label: string;
  /** Optional glyph, always paired with the label so it is never the only cue. */
  glyph?: string;
  disabled?: boolean;
  disabledReason?: string;
}

interface TabsProps<T extends string> {
  items: TabItem<T>[];
  value: T;
  onChange: (next: T) => void;
  /** Labels the tablist for screen readers. */
  label: string;
  children: ReactNode;
}

/**
 * WAI-ARIA tabs with roving focus and arrow-key navigation.
 * Manual activation: arrows move focus, Enter/Space selects — this keeps
 * keyboard users from triggering expensive canvas repaints while scanning.
 */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
  children,
}: TabsProps<T>) {
  const baseId = useId();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const enabled = items.filter((item) => !item.disabled);

  function focusAt(index: number) {
    const target = enabled[(index + enabled.length) % enabled.length];
    if (target) refs.current[target.id]?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, id: T) {
    const index = enabled.findIndex((item) => item.id === id);
    if (index === -1) return;
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        event.preventDefault();
        focusAt(index + 1);
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        event.preventDefault();
        focusAt(index - 1);
        break;
      case 'Home':
        event.preventDefault();
        focusAt(0);
        break;
      case 'End':
        event.preventDefault();
        focusAt(enabled.length - 1);
        break;
      case 'Enter':
      case ' ':
        event.preventDefault();
        onChange(id);
        break;
      default:
        break;
    }
  }

  return (
    <div>
      <div
        role="tablist"
        aria-label={label}
        aria-orientation="horizontal"
        className="flex flex-wrap gap-1 rounded-[10px] border border-line bg-sunken p-1"
      >
        {items.map((item) => {
          const selected = item.id === value;
          return (
            <button
              key={item.id}
              ref={(node) => {
                refs.current[item.id] = node;
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${item.id}`}
              aria-controls={`${baseId}-panel-${item.id}`}
              aria-selected={selected}
              aria-disabled={item.disabled || undefined}
              tabIndex={selected ? 0 : -1}
              disabled={item.disabled}
              title={item.disabled ? item.disabledReason : undefined}
              onClick={() => !item.disabled && onChange(item.id)}
              onKeyDown={(event) => onKeyDown(event, item.id)}
              className={[
                'anim rounded-[7px] px-3 py-1.5 text-[13px] font-medium transition-colors',
                selected
                  ? 'border border-line bg-surface text-ink shadow-card'
                  : 'border border-transparent text-ink-2 hover:text-ink',
                item.disabled ? 'cursor-not-allowed opacity-50 hover:text-ink-2' : '',
              ].join(' ')}
            >
              {item.glyph ? (
                <span aria-hidden="true" className="mr-1.5 font-mono">
                  {item.glyph}
                </span>
              ) : null}
              {item.label}
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={`${baseId}-panel-${value}`}
        aria-labelledby={`${baseId}-tab-${value}`}
        tabIndex={0}
        className="mt-3 rounded-[10px] focus-visible:outline-2"
      >
        {children}
      </div>
    </div>
  );
}
