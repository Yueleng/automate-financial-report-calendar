"use client";

import { useState, useEffect, useRef, useSyncExternalStore } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { fetchJobStatus, triggerRefresh, ApiError } from "@/lib/api";
import { RefreshCwIcon } from "lucide-react";

interface RefreshButtonProps {
  onRefreshComplete?: () => void;
  className?: string;
}

let clockSnapshot = 0;
const clockSubscribers = new Set<() => void>();
let clockTimer: ReturnType<typeof setInterval> | null = null;

function subscribeClock(callback: () => void) {
  clockSubscribers.add(callback);
  if (clockSubscribers.size === 1) {
    clockSnapshot = Date.now();
    clockTimer = setInterval(() => {
      clockSnapshot = Date.now();
      clockSubscribers.forEach((cb) => cb());
    }, 1000);
  }
  callback();
  return () => {
    clockSubscribers.delete(callback);
    if (clockSubscribers.size === 0 && clockTimer) {
      clearInterval(clockTimer);
      clockTimer = null;
    }
  };
}

function getClockSnapshot() {
  return clockSnapshot;
}

function getServerClockSnapshot() {
  return 0;
}

export function RefreshButton({
  onRefreshComplete,
  className,
}: RefreshButtonProps) {
  const [submitting, setSubmitting] = useState(false);
  const prevRunningRef = useRef<boolean | null>(null);
  const now = useSyncExternalStore(
    subscribeClock,
    getClockSnapshot,
    getServerClockSnapshot,
  );

  // get job status
  const { data: status, mutate } = useSWR("/api/jobs/status", fetchJobStatus, {
    refreshInterval: (latest) => (latest?.running ? 1500 : 10000),
    revalidateOnFocus: true,
  });

  const cooldownTime = status?.cooldown_until
    ? new Date(status.cooldown_until).getTime()
    : 0;
  const cooldownSeconds = now
    ? Math.max(0, Math.ceil((cooldownTime - now) / 1000))
    : 0;

  // Detect transition from running to finished
  useEffect(() => {
    if (status) {
      // if the job was running and now it's not, it means it finished
      // then show a toast notification
      if (prevRunningRef.current === true && !status.running) {
        if (status.last_error) {
          toast.error("Refresh failed: " + status.last_error);
        } else {
          toast.success(`Calendar updated: ${status.event_count ?? 0} events.`);

          // after refresh completes, trigger following events
          // e.g. refetch reports and update event list
          onRefreshComplete?.();
        }
      }
      prevRunningRef.current = status.running;
    }
  }, [status, onRefreshComplete]);

  const isRunning = Boolean(status?.running || submitting);
  const isDisabled = isRunning || cooldownSeconds > 0;

  const handleRefresh = async () => {
    if (isDisabled) return;
    setSubmitting(true);
    try {
      await triggerRefresh();
      toast.info("Refresh job started in background...");
      await mutate();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 429) {
          toast.warning("Refresh is in cooldown. Please wait.");
        } else if (err.status === 409) {
          toast.info("A refresh job is already running.");
        } else {
          toast.error(err.message);
        }
      } else {
        toast.error("Failed to trigger refresh.");
      }
      await mutate();
    } finally {
      setSubmitting(false);
    }
  };

  let buttonText = "Refresh Now";
  if (isRunning) {
    buttonText = "Updating...";
  } else if (cooldownSeconds > 0) {
    const mins = Math.floor(cooldownSeconds / 60);
    const secs = cooldownSeconds % 60;
    buttonText = `Cooldown (${mins}:${secs.toString().padStart(2, "0")})`;
  }

  return (
    <Button
      variant="outline"
      size="sm"
      disabled={isDisabled}
      onClick={handleRefresh}
      className={`relative overflow-hidden font-medium border-border/60 hover:bg-accent transition-all ${className}`}
    >
      <RefreshCwIcon
        className={`w-3.5 h-3.5 mr-2 ${isRunning ? "animate-spin text-emerald-400" : "text-muted-foreground"}`}
      />
      <span>{buttonText}</span>
    </Button>
  );
}
