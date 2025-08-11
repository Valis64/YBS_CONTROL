import { useState, useMemo, useEffect } from "react";

function toISOEndOfDay(d: Date) {
  const e = new Date(d); e.setHours(23,59,59,999);
  return e.toISOString();
}
function toISOStartOfDay(d: Date) {
  const s = new Date(d); s.setHours(0,0,0,0);
  return s.toISOString();
}

export type Preset =
  | "today"
  | "yesterday"
  | "last7"
  | "last30"
  | "thisMonth"
  | "lastMonth"
  | "custom";

interface Props {
  onChange: (payload: any) => void;
  disallowFuture?: boolean;
  maxWindowDays?: number;
}

export default function DateRangePicker({ onChange, disallowFuture=false, maxWindowDays }: Props) {
  const [preset, setPreset] = useState<Preset>("last7");
  const [start, setStart] = useState<string>("");
  const [end, setEnd] = useState<string>("");

  // restore from localStorage
  useEffect(() => {
    const saved = localStorage.getItem("dateRangePicker");
    if (saved) {
      try {
        const p = JSON.parse(saved);
        if (p.preset) setPreset(p.preset);
        if (p.start) setStart(p.start);
        if (p.end) setEnd(p.end);
      } catch {}
    }
  }, []);

  // persist
  useEffect(() => {
    localStorage.setItem("dateRangePicker", JSON.stringify({preset, start, end}));
  }, [preset, start, end]);

  const computed = useMemo(() => {
    const n = new Date();
    const y = new Date(n); y.setDate(n.getDate()-1);
    const firstOfThis = new Date(n.getFullYear(), n.getMonth(), 1);
    const firstOfLast = new Date(n.getFullYear(), n.getMonth()-1, 1);
    const endOfLast = new Date(n.getFullYear(), n.getMonth(), 0);

    switch (preset) {
      case "today":     return { s: toISOStartOfDay(n), e: toISOEndOfDay(n) };
      case "yesterday": return { s: toISOStartOfDay(y), e: toISOEndOfDay(y) };
      case "last7": {
        const s = new Date(n); s.setDate(n.getDate()-6);
        return { s: toISOStartOfDay(s), e: toISOEndOfDay(n) };
      }
      case "last30": {
        const s = new Date(n); s.setDate(n.getDate()-29);
        return { s: toISOStartOfDay(s), e: toISOEndOfDay(n) };
      }
      case "thisMonth": return { s: toISOStartOfDay(firstOfThis), e: toISOEndOfDay(n) };
      case "lastMonth": return { s: toISOStartOfDay(firstOfLast), e: toISOEndOfDay(endOfLast) };
      case "custom":    return start && end ? { s: toISOStartOfDay(new Date(start)), e: toISOEndOfDay(new Date(end)) } : { s:"", e:"" };
    }
  }, [preset, start, end]);

  const invalid = computed.s && computed.e ? (new Date(computed.e) < new Date(computed.s)) : false;

  const futureInvalid = disallowFuture && computed.e && new Date(computed.e) > new Date();

  const windowInvalid = maxWindowDays && computed.s && computed.e ? ((new Date(computed.e).getTime() - new Date(computed.s).getTime())/(1000*60*60*24) + 1) > maxWindowDays : false;

  function emit() {
    if (!computed.s || !computed.e || invalid || futureInvalid || windowInvalid) return;
    onChange({
      dateRange: {
        start: computed.s,
        end: computed.e,
        preset: preset === "custom" ? "custom" : preset
      }
    });
  }

  const maxDate = disallowFuture ? new Date().toISOString().slice(0,10) : undefined;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <select value={preset} onChange={e=>setPreset(e.target.value as Preset)} aria-label="Preset">
          <option value="today">Today</option>
          <option value="yesterday">Yesterday</option>
          <option value="last7">Last 7 days</option>
          <option value="last30">Last 30 days</option>
          <option value="thisMonth">This month</option>
          <option value="lastMonth">Last month</option>
          <option value="custom">Custom…</option>
        </select>

        {preset === "custom" && (
          <>
            <input type="date" value={start} onChange={e=>setStart(e.target.value)} aria-label="Start date" max={maxDate} />
            <input type="date" value={end} onChange={e=>setEnd(e.target.value)} aria-label="End date" max={maxDate} />
          </>
        )}
      </div>

      {invalid && <div role="alert">End date must be on or after the start date.</div>}
      {futureInvalid && <div role="alert">Dates in the future are not allowed.</div>}
      {windowInvalid && <div role="alert">Selected range exceeds the allowed window.</div>}

      <button onClick={emit} disabled={!computed.s || !computed.e || invalid || futureInvalid || windowInvalid}>
        Apply
      </button>
    </div>
  );
}
