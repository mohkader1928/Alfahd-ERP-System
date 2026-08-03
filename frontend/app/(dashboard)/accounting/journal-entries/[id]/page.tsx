"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import Link from "next/link";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { accountingApi } from "@/features/accounting/api/client";
import { ApiError } from "@/lib/api-client";
import { sourceDocumentHref, sourceDocumentLabelKey } from "@/lib/source-document-links";

export default function JournalEntryDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const { data, isLoading } = useQuery({
    queryKey: ["journal-entry", companyId, id],
    queryFn: () => accountingApi.getJournalEntry(companyId, id),
  });
  const accountsQuery = useQuery({
    queryKey: ["accounts", companyId],
    queryFn: () => accountingApi.listAccounts(companyId),
  });

  const postMutation = useMutation({
    mutationFn: () => accountingApi.postJournalEntry(companyId, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["journal-entry", companyId, id] });
      queryClient.invalidateQueries({ queryKey: ["journal-entries", companyId] });
    },
  });
  const reverseMutation = useMutation({
    mutationFn: () => accountingApi.reverseJournalEntry(companyId, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["journal-entry", companyId, id] });
      queryClient.invalidateQueries({ queryKey: ["journal-entries", companyId] });
    },
  });

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (!data) return null;

  const { entry, lines } = data;
  const accountLabel = (accountId: string) => {
    const acc = accountsQuery.data?.find((a) => a.id === accountId);
    return acc ? `${acc.code} — ${acc.name}` : accountId;
  };

  return (
    <div className="max-w-2xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/accounting")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            {entry.reference ?? entry.id.slice(0, 8)}
            <Badge variant={entry.status === "posted" ? "default" : "secondary"}>{entry.status}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">{t("accounting.je.date")}</dt>
            <dd>{entry.entry_date}</dd>
            {entry.source_table && (
              <>
                <dt className="text-muted-foreground">{t("accounting.je.source_document")}</dt>
                <dd>
                  {(() => {
                    const href = sourceDocumentHref(entry.source_table, entry.source_id);
                    const labelKey = sourceDocumentLabelKey(entry.source_table);
                    const label = labelKey ? t(labelKey) : entry.source_table;
                    return href ? (
                      <Link href={href} className="underline-offset-4 hover:underline">
                        {label}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">{label}</span>
                    );
                  })()}
                </dd>
              </>
            )}
          </dl>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("accounting.je.account")}</TableHead>
                <TableHead className="text-end">{t("accounting.je.debit")}</TableHead>
                <TableHead className="text-end">{t("accounting.je.credit")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((line) => (
                <TableRow key={line.id}>
                  <TableCell>{accountLabel(line.account_id)}</TableCell>
                  <TableCell className="text-end">{line.debit}</TableCell>
                  <TableCell className="text-end">{line.credit}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {entry.status === "draft" && (
            <Button onClick={() => postMutation.mutate()} disabled={postMutation.isPending}>
              {postMutation.isPending ? t("common.loading") : t("accounting.je.post")}
            </Button>
          )}
          {entry.status === "posted" && (
            <Button variant="outline" onClick={() => reverseMutation.mutate()} disabled={reverseMutation.isPending}>
              {reverseMutation.isPending ? t("common.loading") : t("accounting.je.reverse")}
            </Button>
          )}
          {(postMutation.isError || reverseMutation.isError) && (
            <p className="text-sm text-destructive">
              {(postMutation.error ?? reverseMutation.error) instanceof ApiError
                ? ((postMutation.error ?? reverseMutation.error) as ApiError).detail
                : t("common.error")}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
