"use client";

import { Report } from "@/lib/api";
import { getSymbolColor, RESCHEDULED_STYLE } from "@/lib/colors";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import {
  CalendarIcon,
  TrendingUpIcon,
  AlertTriangleIcon,
  ClockIcon,
} from "lucide-react";

interface EventDialogProps {
  report: Report | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EventDialog({ report, open, onOpenChange }: EventDialogProps) {
  if (!report) return null;

  const color = getSymbolColor(report.symbol);
  const isRescheduled = Boolean(report.rescheduled_to);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md border-border/40 bg-background/95 backdrop-blur-xl p-6 shadow-2xl">
        <DialogHeader className="gap-1.5 pb-2 border-b border-border/40">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span
                className="px-2.5 py-1 text-xs font-semibold rounded-md border tracking-wider"
                style={{
                  backgroundColor: color.bg,
                  borderColor: color.border,
                  color: color.text,
                }}
              >
                {report.symbol}
              </span>
              {isRescheduled && (
                <Badge
                  variant="outline"
                  className={`${RESCHEDULED_STYLE.badge} text-[11px] font-medium flex items-center gap-1`}
                >
                  <AlertTriangleIcon className="w-3 h-3 text-amber-400" />
                  Rescheduled
                </Badge>
              )}
            </div>
          </div>
          <DialogTitle className="text-xl font-bold tracking-tight text-foreground pt-2">
            {report.name || report.symbol}
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Earnings Release Details & Guidance
          </DialogDescription>
        </DialogHeader>

        {isRescheduled && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200 flex items-start gap-2.5">
            <AlertTriangleIcon className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="font-semibold text-amber-300">
                Date Revision Notice
              </p>
              <p>
                Originally scheduled for{" "}
                <span className="font-semibold line-through text-amber-400/80">
                  {report.report_date}
                </span>
                . Rescheduled to{" "}
                <span className="font-bold underline text-amber-200">
                  {report.rescheduled_to}
                </span>
                .
              </p>
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 py-2">
          <div className="rounded-lg border border-border/30 bg-card/50 p-3">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              <CalendarIcon className="w-3.5 h-3.5 text-muted-foreground" />
              <span>Earnings Date</span>
            </div>
            <p className="text-sm font-semibold text-foreground">
              {report.report_date}
            </p>
          </div>

          <div className="rounded-lg border border-border/30 bg-card/50 p-3">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              <ClockIcon className="w-3.5 h-3.5 text-muted-foreground" />
              <span>Fiscal Period End</span>
            </div>
            <p className="text-sm font-semibold text-foreground">
              {report.fiscal_date_ending}
            </p>
          </div>

          <div className="col-span-2 rounded-lg border border-border/30 bg-card/50 p-3">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              <TrendingUpIcon className="w-3.5 h-3.5 text-muted-foreground" />
              <span>Consensus EPS Estimate</span>
            </div>
            <p className="text-base font-semibold text-foreground">
              {report.estimate ? (
                <>
                  <span className="text-emerald-400 font-mono">
                    {report.currency === "USD" ? "$" : ""}
                    {report.estimate}
                  </span>{" "}
                  <span className="text-xs text-muted-foreground font-normal">
                    {report.currency}
                  </span>
                </>
              ) : (
                <span className="text-muted-foreground font-normal text-sm">
                  Not disclosed / consensus pending
                </span>
              )}
            </p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
