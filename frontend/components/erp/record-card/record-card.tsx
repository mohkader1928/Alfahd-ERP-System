"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Breadcrumbs, type BreadcrumbItem } from "@/components/erp/breadcrumbs/breadcrumbs";

export interface RecordCardTab {
  key: string;
  label: string;
  content: React.ReactNode;
}

interface RecordCardProps {
  breadcrumbs?: BreadcrumbItem[];
  name: string;
  code?: string;
  statusBadge?: React.ReactNode;
  primaryActions?: React.ReactNode;
  summary?: { label: string; value: string }[];
  tabs: RecordCardTab[];
  defaultTab?: string;
}

/**
 * Phase 17A shared record/card shell (Part 7) for future Product/Customer/
 * Vendor/Account cards — header (name/code/status/actions), summary KPI
 * strip, then tabs (Overview/Transactions/Documents/Balances/History/
 * Activity, caller-supplied). Tab visibility is controlled manually
 * (`tab === key && content`), not left to Base UI's Tabs.Panel — see the
 * same documented workaround in accounting/inventory/purchasing pages:
 * Tabs.Panel doesn't reliably hide inactive panels once a second one
 * mounts, so every ERP screen in this codebase sidesteps it the same way.
 */
export function RecordCard({ breadcrumbs, name, code, statusBadge, primaryActions, summary, tabs, defaultTab }: RecordCardProps) {
  const [tab, setTab] = useState(defaultTab ?? tabs[0]?.key);

  return (
    <div className="space-y-4">
      {breadcrumbs && <Breadcrumbs items={breadcrumbs} />}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold">{name}</h1>
          {code && <span className="font-mono text-sm text-muted-foreground">{code}</span>}
          {statusBadge}
        </div>
        {primaryActions && <div className="flex items-center gap-2">{primaryActions}</div>}
      </div>

      {summary && summary.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {summary.map((item) => (
            <Card key={item.label}>
              <CardContent className="pt-4">
                <p className="text-xs text-muted-foreground">{item.label}</p>
                <p className="text-lg font-semibold tabular-nums">{item.value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Tabs value={tab} onValueChange={(v) => setTab(v as string)}>
        <TabsList>
          {tabs.map((t) => (
            <TabsTrigger key={t.key} value={t.key}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabs.map((t) => (
          <TabsContent key={t.key} value={t.key}>
            {tab === t.key && t.content}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
