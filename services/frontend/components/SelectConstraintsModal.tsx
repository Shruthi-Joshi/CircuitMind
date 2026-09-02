"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, ShieldAlert, Sparkles, Sliders, Info, X } from "lucide-react";

// Parameter definitions with metadata and type rules.
//
// `backendDimension` maps each UI parameter to the constraint *dimension* the
// backend actually enforces (see ALLOWED_CONSTRAINTS in the API /
// alternate_match.COLUMN_MAPPING). The backend uses "must match original"
// semantics — it resolves the required value from each line item's original
// component — so the typed values below are captured for UI clarity but only
// the mapped dimension name is sent. Parameters with `backendDimension: null`
// are not yet enforceable and are shown as informational only.
export interface ParameterSpec {
  key: string;
  label: string;
  category: "Physical" | "Electrical" | "Thermal" | "General";
  type: "exact" | "min" | "max";
  unit?: string;
  placeholder: string;
  backendDimension: string | null;
}

const AVAILABLE_PARAMETERS: ParameterSpec[] = [
  { key: "package", label: "Package / Footprint", category: "Physical", type: "exact", placeholder: "e.g., LQFP-48, 0603, QFN-32", backendDimension: "package" },
  { key: "pin_count", label: "Pin Count", category: "Physical", type: "exact", placeholder: "e.g., 48", backendDimension: "pin_count" },
  { key: "mounting_type", label: "Mounting Style", category: "Physical", type: "exact", placeholder: "e.g., Surface Mount, Through Hole", backendDimension: null },
  { key: "voltage_max", label: "Max Operating Voltage", category: "Electrical", type: "max", unit: "V", placeholder: "e.g., 3.3", backendDimension: "voltage" },
  { key: "voltage_min", label: "Min Operating Voltage", category: "Electrical", type: "min", unit: "V", placeholder: "e.g., 1.8", backendDimension: "voltage" },
  { key: "resistance", label: "Resistance", category: "Electrical", type: "exact", unit: "Ω", placeholder: "e.g., 10k", backendDimension: null },
  { key: "capacitance", label: "Capacitance", category: "Electrical", type: "exact", unit: "F", placeholder: "e.g., 100nF", backendDimension: null },
  { key: "frequency_max", label: "Max Clock Frequency", category: "Electrical", type: "max", unit: "MHz", placeholder: "e.g., 72", backendDimension: null },
  { key: "temp_max", label: "Max Operating Temp", category: "Thermal", type: "max", unit: "°C", placeholder: "e.g., 85", backendDimension: null },
  { key: "manufacturer", label: "Preferred Manufacturer", category: "General", type: "exact", placeholder: "e.g., STMicroelectronics", backendDimension: "manufacturer" },
];

/**
 * Reduce the modal's selected UI parameter keys down to the de-duplicated set
 * of backend constraint dimension names (legacy "match original" mode). Kept
 * for reference; the value-based flow uses {@link toValueConstraints} instead.
 */
export function toBackendDimensions(selectedKeys: string[]): string[] {
  const dims = new Set<string>();
  selectedKeys.forEach((key) => {
    const spec = AVAILABLE_PARAMETERS.find((p) => p.key === key);
    if (spec?.backendDimension) dims.add(spec.backendDimension);
  });
  return Array.from(dims);
}

/**
 * Build the value-based constraints map the backend enforces:
 * ``{ key: typedValue }`` for each selected parameter that has a value.
 * Numeric-looking values are coerced to numbers so the backend's min/max
 * threshold comparisons work as intended.
 */
export function toValueConstraints(
  selectedKeys: string[],
  paramValues: Record<string, string>
): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  selectedKeys.forEach((key) => {
    const raw = (paramValues[key] ?? "").trim();
    if (!raw) return;
    const num = Number(raw);
    out[key] = raw !== "" && !Number.isNaN(num) ? num : raw;
  });
  return out;
}

interface SelectConstraintsModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Receives the typed value-based constraints map, e.g. {package:"LQFP-48", voltage_max:3.3}. */
  onSubmitConstraints: (constraints: Record<string, string | number>) => void;
}

export default function SelectConstraintsModal({
  isOpen,
  onClose,
  onSubmitConstraints,
}: SelectConstraintsModalProps) {
  const [selectedKeys, setSelectedKeys] = useState<string[]>(["package", "pin_count", "voltage_max"]);
  const [paramValues, setParamValues] = useState<Record<string, string>>({
    package: "LQFP-48",
    pin_count: "48",
    voltage_max: "3.3",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const toggleSelectKey = (key: string) => {
    if (selectedKeys.includes(key)) {
      setSelectedKeys(selectedKeys.filter((k) => k !== key));
      const updatedValues = { ...paramValues };
      delete updatedValues[key];
      setParamValues(updatedValues);
    } else {
      if (selectedKeys.length >= 5) return; // Enforce max 5 constraints
      setSelectedKeys([...selectedKeys, key]);
    }
  };

  const handleValueChange = (key: string, value: string) => {
    setParamValues((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      // Value-based thresholds: send the engineer's typed target values keyed
      // by parameter. The backend enforces exact/min/max per parameter and
      // drops any candidate that violates them.
      onSubmitConstraints(toValueConstraints(selectedKeys, paramValues));
      onClose();
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          className="relative w-full max-w-3xl rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl"
        >
          {/* Header */}
          <div className="flex items-start justify-between border-b border-slate-800 pb-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                <Sliders className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
                  Non-Negotiable Constraints
                  <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                    {selectedKeys.length} / 5 Selected
                  </span>
                </h2>
                <p className="text-sm text-slate-400">
                  Select up to 5 critical parameters that candidate alternates must satisfy.
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="mt-6 space-y-6">
            {/* Step 1: Parameter Selection Pills */}
            <div>
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-400 block mb-3">
                1. Select Critical Parameters (Max 5)
              </label>
              <div className="flex flex-wrap gap-2">
                {AVAILABLE_PARAMETERS.map((param) => {
                  const isSelected = selectedKeys.includes(param.key);
                  const isDisabled = !isSelected && selectedKeys.length >= 5;

                  return (
                    <button
                      key={param.key}
                      type="button"
                      disabled={isDisabled}
                      onClick={() => toggleSelectKey(param.key)}
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                        isSelected
                          ? "bg-cyan-500/20 border border-cyan-400/50 text-cyan-200 shadow-sm shadow-cyan-500/10"
                          : isDisabled
                          ? "bg-slate-800/40 border border-slate-800 text-slate-600 cursor-not-allowed"
                          : "bg-slate-800/80 border border-slate-700/60 text-slate-300 hover:border-slate-500 hover:bg-slate-800"
                      }`}
                    >
                      {isSelected ? <Check className="h-3.5 w-3.5 text-cyan-400" /> : null}
                      {param.label}
                      {param.backendDimension === null && (
                        <span
                          title="Enforced best-effort: only applied when catalog data exposes this spec"
                          className="ml-1 rounded bg-slate-700/60 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-slate-400"
                        >
                          best-effort
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Step 2: Value Constraints Form Input */}
            <div>
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-400 block mb-3">
                2. Specify Target Values & Thresholds
              </label>

              {selectedKeys.length === 0 ? (
                <div className="flex items-center gap-3 rounded-xl border border-dashed border-slate-800 p-4 bg-slate-950/40 text-slate-500 text-sm">
                  <Info className="h-5 w-5 text-slate-600" />
                  Select at least one parameter above to enforce hard filtering constraints.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-h-[260px] overflow-y-auto pr-2">
                  {selectedKeys.map((key) => {
                    const spec = AVAILABLE_PARAMETERS.find((p) => p.key === key)!;
                    return (
                      <div
                        key={key}
                        className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5 space-y-2"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-slate-200">{spec.label}</span>
                          <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                            Rule: {spec.type}
                          </span>
                        </div>
                        <div className="relative">
                          <input
                            type="text"
                            required
                            value={paramValues[key] || ""}
                            onChange={(e) => handleValueChange(key, e.target.value)}
                            placeholder={spec.placeholder}
                            className="w-full rounded-lg border border-slate-700/80 bg-slate-900 px-3 py-2 text-xs text-slate-100 placeholder-slate-600 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 transition-colors"
                          />
                          {spec.unit && (
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-mono text-slate-500">
                              {spec.unit}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Warning Banner */}
            <div className="flex items-start gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3.5 text-xs text-amber-300">
              <ShieldAlert className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
              <span>
                Enforcing rigid constraints will exclude any candidates that do not strictly match these bounds, regardless of overall vector similarity.
              </span>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 pt-2 border-t border-slate-800">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting || selectedKeys.length === 0}
                className="flex items-center gap-2 rounded-xl bg-cyan-500 px-5 py-2.5 text-xs font-semibold text-slate-950 hover:bg-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:opacity-50 transition-all shadow-lg shadow-cyan-500/20"
              >
                {isSubmitting ? (
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-950 border-t-transparent" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                Apply Constraints
              </button>
            </div>
          </form>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}