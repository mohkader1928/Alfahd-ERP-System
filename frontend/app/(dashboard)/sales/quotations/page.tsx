"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { salesApi } from "@/features/sales/api/client";

export default function QuotationsPage() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const { data, isLoading } = useQuery({
    queryKey: ["quotations", companyId],
    queryFn: () => salesApi.listQuotations(companyId),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t("sales.quotations.title")}</h1>
        <Button render={<Link href="/sales/quotations/new" />}>
          <Plus className="h-4 w-4" />
          {t("sales.quotations.new")}
        </Button>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("sales.quotations.number")}</TableHead>
            <TableHead>{t("sales.quotations.date")}</TableHead>
            <TableHead>{t("sales.quotations.status")}</TableHead>
            <TableHead className="text-end">{t("sales.quotations.total")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading &&
            Array.from({ length: 3 }).map((_, i) => (
              <TableRow key={i}>
                <TableCell colSpan={4}>
                  <Skeleton className="h-6 w-full" />
                </TableCell>
              </TableRow>
            ))}
          {!isLoading && data?.length === 0 && (
            <TableRow>
              <TableCell colSpan={4} className="text-center text-muted-foreground">
                {t("common.empty")}
              </TableCell>
            </TableRow>
          )}
          {data?.map((q) => (
            <TableRow key={q.id}>
              <TableCell>
                <Link href={`/sales/quotations/${q.id}`} className="font-medium underline-offset-4 hover:underline">
                  {q.number}
                </Link>
              </TableCell>
              <TableCell>{q.quote_date}</TableCell>
              <TableCell>
                <Badge variant={q.status === "confirmed" ? "default" : "secondary"}>{q.status}</Badge>
              </TableCell>
              <TableCell className="text-end">{q.total_amount}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
