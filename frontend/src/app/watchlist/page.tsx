"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import {
  fetchWatchlist,
  addWatchlistItem,
  removeWatchlistItem,
  ApiError,
} from "@/lib/api";
import { getSymbolColor } from "@/lib/colors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ListFilterIcon,
  PlusIcon,
  Trash2Icon,
  ShieldAlertIcon,
  InfoIcon,
} from "lucide-react";

export default function WatchlistPage() {
  const { data, isLoading, mutate } = useSWR("/api/watchlist", fetchWatchlist);
  const items = data?.items ?? [];

  const [symbolInput, setSymbolInput] = useState("");
  const [nameInput, setNameInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanSymbol = symbolInput.trim().toUpperCase();
    const cleanName = nameInput.trim();

    if (!cleanSymbol) {
      toast.warning("Please enter a stock ticker symbol.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await addWatchlistItem({
        symbol: cleanSymbol,
        name: cleanName || cleanSymbol,
      });
      await mutate(res, false);
      setSymbolInput("");
      setNameInput("");
      toast.success(`Added ${cleanSymbol} to watchlist`, {
        description: res.refiltered
          ? "Calendar events re-filtered instantly from local cache."
          : "Saved. Events will sync on next provider refresh.",
      });
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        toast.error(err.message);
      } else {
        toast.error("Failed to add company to watchlist.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const symbol = deleteTarget;
    setDeleteTarget(null);

    try {
      const res = await removeWatchlistItem(symbol);
      await mutate(res, false);
      toast.success(`Removed ${symbol} from watchlist`, {
        description: "Calendar events updated accordingly.",
      });
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        toast.error(err.message);
      } else {
        toast.error("Failed to delete company from watchlist.");
      }
    }
  };

  return (
    <div className="max-w-5xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border/40">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <ListFilterIcon className="w-6 h-6 text-blue-400" />
            Watchlist Settings
          </h1>
          <p className="text-xs text-muted-foreground mt-1">
            Companies tracked in{" "}
            <code className="text-foreground/80 font-mono">watchlist.csv</code>{" "}
            and exported to the calendar feed
          </p>
        </div>
      </div>

      {/* Info Banner */}
      <div className="rounded-xl border border-blue-500/20 bg-blue-500/10 p-4 text-xs text-blue-200 flex items-start gap-3">
        <InfoIcon className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="font-semibold text-blue-300">Fast Local Re-filtering</p>
          <p className="text-blue-200/90 leading-relaxed">
            Adding or removing companies immediately updates your calendar by
            re-filtering the cached market data, consuming <strong>zero</strong>{" "}
            Alpha Vantage API calls. Changes are saved directly to{" "}
            <code className="text-blue-100 font-mono">watchlist.csv</code>.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Add Company Form */}
        <Card className="border-border/40 bg-card/40 backdrop-blur-md shadow-lg h-fit">
          <CardHeader>
            <CardTitle className="text-base text-foreground flex items-center gap-2">
              <PlusIcon className="w-4 h-4 text-emerald-400" />
              Add Company
            </CardTitle>
            <CardDescription className="text-xs text-muted-foreground">
              Track a new corporate ticker symbol
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleAdd} className="space-y-3.5">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground/80">
                  Symbol <span className="text-rose-400">*</span>
                </label>
                <Input
                  placeholder="e.g. NVDA, AAPL"
                  value={symbolInput}
                  onChange={(e) => setSymbolInput(e.target.value.toUpperCase())}
                  disabled={submitting}
                  className="bg-background/60 border-border/60 text-sm font-mono uppercase"
                  maxLength={15}
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground/80">
                  Company Name (optional)
                </label>
                <Input
                  placeholder="e.g. NVIDIA Corporation"
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  disabled={submitting}
                  className="bg-background/60 border-border/60 text-sm"
                  maxLength={100}
                />
              </div>

              <Button
                type="submit"
                disabled={submitting || !symbolInput.trim()}
                className="w-full bg-blue-600 hover:bg-blue-500 text-white font-medium text-xs mt-2"
              >
                {submitting ? "Adding..." : "Add to Watchlist"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Watchlist Table */}
        <Card className="md:col-span-2 border-border/40 bg-card/40 backdrop-blur-md shadow-lg overflow-hidden">
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <div>
              <CardTitle className="text-base text-foreground">
                Tracked Companies ({items.length})
              </CardTitle>
              <CardDescription className="text-xs text-muted-foreground">
                Active symbols queried during calendar synchronizations
              </CardDescription>
            </div>
          </CardHeader>

          <CardContent className="p-0">
            {isLoading ? (
              <div className="p-4 space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full bg-zinc-800" />
                ))}
              </div>
            ) : items.length === 0 ? (
              <div className="py-12 text-center space-y-2">
                <ShieldAlertIcon className="w-8 h-8 text-zinc-600 mx-auto" />
                <p className="text-sm text-muted-foreground">
                  No symbols on your watchlist
                </p>
                <p className="text-xs text-muted-foreground">
                  Add at least one stock ticker to begin tracking earnings.
                </p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="border-border/40 hover:bg-transparent">
                    <TableHead className="w-28 text-xs font-semibold text-muted-foreground">
                      Symbol
                    </TableHead>
                    <TableHead className="text-xs font-semibold text-muted-foreground">
                      Company Name
                    </TableHead>
                    <TableHead className="w-16 text-right text-xs font-semibold text-muted-foreground pr-4">
                      Action
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((item) => {
                    const color = getSymbolColor(item.symbol);
                    return (
                      <TableRow
                        key={item.symbol}
                        className="border-border/30 hover:bg-zinc-800/30 transition-colors"
                      >
                        <TableCell className="font-mono py-2.5">
                          <span
                            className="inline-block px-2 py-0.5 text-xs font-semibold rounded border"
                            style={{
                              backgroundColor: color.bg,
                              borderColor: color.border,
                              color: color.text,
                            }}
                          >
                            {item.symbol}
                          </span>
                        </TableCell>
                        <TableCell className="text-sm text-foreground py-2.5">
                          {item.name || item.symbol}
                        </TableCell>
                        <TableCell className="text-right py-2.5 pr-4">
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => setDeleteTarget(item.symbol)}
                            disabled={items.length <= 1}
                            className="text-muted-foreground hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                            title={
                              items.length <= 1
                                ? "Watchlist must keep at least 1 symbol"
                                : `Remove ${item.symbol}`
                            }
                          >
                            <Trash2Icon className="w-3.5 h-3.5" />
                            <span className="sr-only">Delete</span>
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Delete Confirmation Alert */}
      <AlertDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent className="bg-background border-border/60">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-foreground">
              Remove {deleteTarget} from watchlist?
            </AlertDialogTitle>
            <AlertDialogDescription className="text-muted-foreground text-xs">
              This will remove {deleteTarget} from your tracked earnings list
              and re-filter your local calendar events. You can add it back
              anytime.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="bg-transparent border-zinc-700 hover:bg-zinc-800 text-foreground/80">
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDelete}
              className="bg-rose-600 hover:bg-rose-500 text-white"
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
