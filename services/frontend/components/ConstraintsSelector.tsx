"use client";

import { CONSTRAINT_OPTIONS } from "@/lib/api";

interface Props {
  selected: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}

/**
 * Lets the user mark which spec dimensions are *non-negotiable* for a
 * substitution. Each selected dimension forces any proposed alternate to match
 * the original part on that dimension ("must match original" semantics).
 */
export default function ConstraintsSelector({
  selected,
  onChange,
  disabled,
}: Props) {
  const toggle = (key: string) => {
    if (disabled) return;
    onChange(
      selected.includes(key)
        ? selected.filter((k) => k !== key)
        : [...selected, key]
    );
  };

  return (
    <fieldset
      className="mt-4 rounded-lg border border-circuit-border bg-circuit-panel p-4"
      disabled={disabled}
    >
      <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
        Critical constraints (must match original)
      </legend>
      <p className="mb-3 text-xs text-gray-500">
        Optional. Any dimension you require here becomes a hard filter — proposed
        replacements must match the original part on it.
      </p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {CONSTRAINT_OPTIONS.map((opt) => {
          const active = selected.includes(opt.key);
          return (
            <label
              key={opt.key}
              className={[
                "flex cursor-pointer items-start gap-2 rounded border px-3 py-2 text-sm transition",
                active
                  ? "border-circuit-accent bg-circuit-accent/10"
                  : "border-circuit-border hover:border-circuit-accent/60",
                disabled ? "cursor-not-allowed opacity-50" : "",
              ].join(" ")}
            >
              <input
                type="checkbox"
                className="mt-0.5 accent-circuit-accent"
                checked={active}
                onChange={() => toggle(opt.key)}
                disabled={disabled}
                aria-label={opt.label}
              />
              <span>
                <span className="block text-gray-200">{opt.label}</span>
                <span className="block text-xs text-gray-500">{opt.hint}</span>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
