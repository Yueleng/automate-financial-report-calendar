"use client";

import { useState, useMemo } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { ApiError, fetchReports, getCalendarIcsUrl } from "@/lib/api";
import { EarningsCalendar } from "@/components/earnings-calendar";
import { SymbolFilter } from "@/components/symbol-filter";
import { RefreshButton } from "@/components/refresh-button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { CalendarIcon, Share2Icon, ClockIcon } from "lucide-react";

export default function CalendarPage() {
  // get reports data
  const { data, error, isLoading, mutate } = useSWR(
    "/api/reports",
    // a complete request without params,
    // it fetches all upcoming reports as of now.
    () => fetchReports(),
    {
      // When the user clicks back to the browser tab/window,
      // SWR automatically refetches in the background
      // to keep the calendar data up-to-date.
      revalidateOnFocus: true,
    },
  );

  // derive the reports data from the fetched data
  const reports = useMemo(() => data?.reports ?? [], [data]);
  const updatedAt = data?.updated_at ?? null;

  // Track what the user *hid* (not what is selected) so that symbols added later
  // or appearing after a refresh are visible by default.
  const [hiddenSymbols, setHiddenSymbols] = useState<string[]>([]);

  // derive the all symbols from the reports data
  const allSymbols = useMemo(() => {
    return Array.from(new Set(reports.map((r) => r.symbol))).sort();
  }, [reports]);

  // derive the active selected symbols from the all symbols and hidden symbols
  // algo: allSymbols - hiddenSymbols
  const activeSelectedSymbols = useMemo(
    () => allSymbols.filter((s) => !hiddenSymbols.includes(s)),
    [allSymbols, hiddenSymbols],
  );

  // count how many reports each symbol has
  // represented as symbol: count, e.g.{"MSFT": 1, "AAPL": 2, ...}
  const symbolCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of reports) {
      counts[r.symbol] = (counts[r.symbol] || 0) + 1;
    }
    return counts;
  }, [reports]);

  // get filtered reports data (with the active selected symbols)
  const filteredReports = useMemo(() => {
    if (activeSelectedSymbols.length === 0) return [];
    // The new Set here isn't for deduplication—it is solely for O(1) lookup performance
    const set = new Set(activeSelectedSymbols);
    return reports.filter((r) => set.has(r.symbol));
  }, [reports, activeSelectedSymbols]);

  // set hidden filters
  const handleFilterChange = (symbols: string[]) => {
    setHiddenSymbols(allSymbols.filter((s) => !symbols.includes(s)));
  };

  // copy the full calendar .ics URL to the clipboard
  const handleCopyIcs = async () => {
    const fullUrl = `${window.location.origin}${getCalendarIcsUrl()}`;
    try {
      // try to copy the full URL to the clipboard
      await navigator.clipboard.writeText(fullUrl);
      toast.success("iCalendar (.ics) feed URL copied to clipboard!", {
        description: fullUrl,
      });
    } catch {
      // if the clipboard API is not available, show the full URL in the toast
      toast.error("Could not copy automatically. Copy the URL manually:", {
        description: fullUrl,
      });
    }
  };

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Top Header / Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border/40">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <CalendarIcon className="w-6 h-6 text-blue-400" />
            Earnings Release Calendar
          </h1>
          <div className="flex items-center gap-3 mt-1.5 text-xs text-muted-foreground">
            <span>
              {reports.length} report{reports.length === 1 ? "" : "s"} scheduled
            </span>
            {updatedAt && (
              <>
                <span className="text-zinc-600">•</span>
                <span className="flex items-center gap-1">
                  <ClockIcon className="w-3 h-3 text-muted-foreground" />
                  Last synced: {new Date(updatedAt).toLocaleString()}
                </span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <TooltipProvider>
            <Tooltip>
              {/* `asChild` prevents TooltipTrigger from rendering its own default <button>,
                  passing props and ARIA attributes directly to the child <Button> to avoid
                  rendering nested <button> elements in the DOM. */}
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCopyIcs}
                  className="border-border/60 hover:bg-accent text-foreground/80"
                >
                  <Share2Icon className="w-3.5 h-3.5 mr-1.5 text-muted-foreground" />
                  Subscribe (.ics)
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                Copy the .ics feed URL to subscribe in Google/Apple Calendar
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>

          <RefreshButton onRefreshComplete={() => mutate()} />
        </div>
      </div>

      {/* Filter Chips */}
      {!isLoading && allSymbols.length > 0 && (
        <div className="rounded-xl border border-border/40 bg-card/40 p-3.5 backdrop-blur-sm">
          <SymbolFilter
            symbols={allSymbols}
            selectedSymbols={activeSelectedSymbols}
            counts={symbolCounts}
            onChange={handleFilterChange}
          />
        </div>
      )}

      {/* Main Calendar View */}
      <Card className="border-border/40 bg-card/30 backdrop-blur-md overflow-hidden shadow-xl">
        <CardContent className="p-4 sm:p-6">
          {isLoading ? (
            <div className="space-y-4 py-8">
              <div className="flex justify-between items-center">
                <Skeleton className="h-8 w-48 bg-zinc-800" />
                <Skeleton className="h-8 w-64 bg-zinc-800" />
              </div>
              <div className="grid grid-cols-7 gap-2">
                {Array.from({ length: 35 }).map((_, i) => (
                  <Skeleton
                    key={i}
                    className="h-24 bg-zinc-800/60 rounded-md"
                  />
                ))}
              </div>
            </div>
          ) : error ? (
            <div className="text-center py-16 space-y-3">
              <CalendarIcon className="w-12 h-12 text-rose-500 mx-auto" />
              <h3 className="text-lg font-medium text-foreground/80">
                Failed to load reports
              </h3>
              <p className="text-sm text-muted-foreground max-w-md mx-auto">
                {error instanceof ApiError
                  ? `The API returned an error: ${error.message}`
                  : "Unable to connect to the backend API. Ensure the backend server is running on port 8000."}
              </p>
            </div>
          ) : reports.length === 0 ? (
            <div className="text-center py-16 space-y-3">
              <CalendarIcon className="w-12 h-12 text-zinc-600 mx-auto" />
              <h3 className="text-lg font-medium text-foreground/80">
                No earnings events found
              </h3>
              <p className="text-sm text-muted-foreground max-w-md mx-auto">
                No financial reports are currently stored. Click &quot;Refresh
                Now&quot; to fetch the latest market schedule from Alpha
                Vantage, or check your Watchlist.
              </p>
            </div>
          ) : (
            <EarningsCalendar reports={filteredReports} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
