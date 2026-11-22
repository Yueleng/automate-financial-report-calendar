"use client";

import { useMemo, useState } from "react";
import "temporal-polyfill";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/react/daygrid";
import timeGridPlugin from "@fullcalendar/react/timegrid";
import listPlugin from "@fullcalendar/react/list";
import interactionPlugin from "@fullcalendar/react/interaction";
import formaTheme from "@fullcalendar/react/themes/forma";
import "@fullcalendar/react/skeleton.css";
import "@fullcalendar/react/themes/forma/theme.css";

import { Report } from "@/lib/api";
import { getSymbolColor, RESCHEDULED_STYLE } from "@/lib/colors";
import { EventDialog } from "@/components/event-dialog";
import { AlertCircleIcon, PaperclipIcon } from "lucide-react";

import type { EventClickInfo } from "@fullcalendar/react";

interface EarningsCalendarProps {
  reports: Report[];
  onReportsChange?: () => void | Promise<unknown>;
}

export function EarningsCalendar({
  reports,
  onReportsChange,
}: EarningsCalendarProps) {
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const selectedReport = useMemo(
    () => reports.find((r) => r.id === selectedReportId) ?? null,
    [reports, selectedReportId],
  );

  const events = useMemo(() => {
    return reports.map((r) => ({
      id: r.id,
      title:
        r.name && r.name !== r.symbol ? `${r.symbol} · ${r.name}` : r.symbol,
      start: r.report_date,
      allDay: true,
      extendedProps: {
        report: r,
      },
    }));
  }, [reports]);

  const handleEventClick = (info: EventClickInfo) => {
    const report = info.event.extendedProps?.report as Report | undefined;
    if (report && !report.rescheduled_to) {
      setSelectedReportId(report.id);
      setDialogOpen(true);
    }
  };

  return (
    <div className="w-full relative earnings-calendar-wrapper">
      <FullCalendar
        plugins={[
          formaTheme,
          dayGridPlugin,
          timeGridPlugin,
          listPlugin,
          interactionPlugin,
        ]}
        initialView="dayGridMonth"
        colorScheme="dark"
        dayHeaderFormat={{ weekday: "short" }}
        headerToolbar={{
          left: "prev,next today",
          center: "title",
          right: "dayGridMonth,timeGridWeek,listMonth",
        }}
        events={events}
        eventClick={handleEventClick}
        dayMaxEvents={3}
        height="auto"
        eventContent={(eventInfo) => {
          const report: Report = eventInfo.event.extendedProps.report;
          if (!report) return null;

          const color = getSymbolColor(report.symbol);

          if (report.rescheduled_to) {
            const arrow =
              report.report_date > report.rescheduled_to ? "←" : "→";
            return (
              <div
                className="w-full truncate px-2 py-1 text-xs rounded border transition-all cursor-default flex items-center justify-between gap-1 shadow-sm"
                style={{
                  backgroundColor: RESCHEDULED_STYLE.bg,
                  borderColor: RESCHEDULED_STYLE.border,
                  borderStyle: RESCHEDULED_STYLE.borderStyle as "dashed",
                  color: RESCHEDULED_STYLE.text,
                }}
              >
                <div className="flex items-center gap-1.5 truncate">
                  <AlertCircleIcon className="w-3 h-3 text-amber-400 shrink-0" />
                  <span className="font-semibold line-through text-amber-300/80">
                    {report.symbol}
                  </span>
                  {report.name && report.name !== report.symbol && (
                    <span className="truncate opacity-70 hidden sm:inline line-through">
                      {report.name}
                    </span>
                  )}
                </div>
                <span className="text-[10px] bg-amber-500/20 px-1 py-0.2 rounded border border-amber-500/30 text-amber-200 font-mono shrink-0">
                  {arrow} {report.rescheduled_to}
                </span>
              </div>
            );
          }

          return (
            <div
              className="w-full truncate px-2 py-1 text-xs rounded border transition-all hover:brightness-110 cursor-pointer flex items-center justify-between gap-1 shadow-sm"
              style={{
                backgroundColor: color.bg,
                borderColor: color.border,
                color: color.text,
              }}
            >
              <div className="flex items-center gap-1.5 truncate">
                <span className="font-bold tracking-tight">
                  {report.symbol}
                </span>
                {report.name && report.name !== report.symbol && (
                  <span className="truncate opacity-80 hidden sm:inline">
                    {report.name}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {report.attachments?.length > 0 && (
                  <span
                    className="inline-flex items-center gap-0.5 text-[10px] opacity-90 font-mono bg-black/25 px-1 rounded"
                    title={`${report.attachments.length} PDF report${report.attachments.length === 1 ? "" : "s"} attached`}
                  >
                    <PaperclipIcon className="w-2.5 h-2.5" />
                    {report.attachments.length}
                  </span>
                )}
                {report.estimate && (
                  <span className="text-[10px] opacity-90 font-mono bg-black/20 px-1 rounded">
                    {report.currency === "USD" ? "$" : ""}
                    {report.estimate}
                  </span>
                )}
              </div>
            </div>
          );
        }}
      />

      <EventDialog
        report={selectedReport}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onAttachmentsChange={onReportsChange}
      />
    </div>
  );
}
