"use client";

import type { ResultsResponse } from "@/lib/api";

interface Props {
  results: ResultsResponse;
}

export default function ResultsPanel({ results }: Props) {
  const { purchase_orders, total_cost } = results;

  // Group POs by supplier for the "split order" view.
  const bySupplier = purchase_orders.reduce<Record<string, typeof purchase_orders>>(
    (acc, po) => {
      const key = po.supplier || "Unknown";
      (acc[key] ||= []).push(po);
      return acc;
    },
    {}
  );

  const maxLead = purchase_orders.reduce(
    (m, po) => Math.max(m, po.lead_time_days),
    0
  );

  return (
    <div className="rounded-lg border border-circuit-border bg-circuit-panel">
      <div className="flex items-center justify-between border-b border-circuit-border px-4 py-3">
        <h3 className="text-sm font-semibold text-circuit-green">
          ✓ Split Purchase Orders
        </h3>
        <div className="flex gap-4 text-xs text-gray-400">
          <span>
            Total:{" "}
            <span className="font-semibold text-circuit-green">
              ${total_cost.toFixed(2)}
            </span>
          </span>
          <span>
            Max lead:{" "}
            <span className="font-semibold text-gray-200">{maxLead}d</span>
          </span>
        </div>
      </div>

      <div className="p-4">
        {purchase_orders.length === 0 ? (
          <p className="text-xs text-gray-500">No purchase orders generated.</p>
        ) : (
          Object.entries(bySupplier).map(([supplier, pos]) => {
            const subtotal = pos.reduce((s, p) => s + p.total_price, 0);
            return (
              <div key={supplier} className="mb-4">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-semibold text-circuit-accent">
                    {supplier}
                  </span>
                  <span className="text-xs text-gray-400">
                    subtotal ${subtotal.toFixed(2)}
                  </span>
                </div>
                <table className="w-full text-left text-xs">
                  <thead className="text-gray-500">
                    <tr>
                      <th className="pb-1">MPN</th>
                      <th className="pb-1 text-right">Qty</th>
                      <th className="pb-1 text-right">Unit</th>
                      <th className="pb-1 text-right">Total</th>
                      <th className="pb-1 text-right">Lead</th>
                    </tr>
                  </thead>
                  <tbody className="text-gray-300">
                    {pos.map((po, i) => (
                      <tr key={i} className="border-t border-circuit-border/50">
                        <td className="py-1">{po.component_mpn}</td>
                        <td className="py-1 text-right">{po.quantity}</td>
                        <td className="py-1 text-right">
                          ${po.unit_price.toFixed(3)}
                        </td>
                        <td className="py-1 text-right">
                          ${po.total_price.toFixed(2)}
                        </td>
                        <td className="py-1 text-right">
                          {po.lead_time_days}d
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
