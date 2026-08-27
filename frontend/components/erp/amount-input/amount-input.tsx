"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";

/**
 * Owner request: every screen that records a monetary amount (Journal
 * Entry debit/credit, Payments/Customer Receipts/Vendor Payments) should
 * display it with standard thousands-grouping (e.g. "1,000,000"), not a
 * bare digit string. Standard technique, no new dependency: the
 * underlying value stays a plain numeric string (what the rest of the
 * form/API already expects) at all times; only the *display* text differs
 * -- raw digits while the field has focus (so typing/cursor position is
 * never disrupted), grouped with `toLocaleString("en-US")` once it blurs.
 * Same "en-US" grouping `formatCurrency` already uses everywhere else in
 * this app (lib/format-currency.ts) -- Western digit grouping regardless
 * of locale is the established convention for financial figures here.
 */
function formatForDisplay(raw: string): string {
  const num = Number(raw);
  if (raw.trim() === "" || !Number.isFinite(num)) return raw;
  return num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

interface AmountInputProps extends Omit<React.ComponentProps<typeof Input>, "value" | "onChange" | "type"> {
  value: string;
  onChange: (value: string) => void;
}

export function AmountInput({ value, onChange, onFocus, onBlur, ...props }: AmountInputProps) {
  const [focused, setFocused] = useState(false);

  return (
    <Input
      {...props}
      type="text"
      inputMode="decimal"
      value={focused ? value : formatForDisplay(value)}
      onChange={(e) => onChange(e.target.value.replace(/,/g, ""))}
      onFocus={(e) => {
        setFocused(true);
        onFocus?.(e);
      }}
      onBlur={(e) => {
        setFocused(false);
        onBlur?.(e);
      }}
    />
  );
}
