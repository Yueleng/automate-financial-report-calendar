export interface Report {
  id: string;
  symbol: string;
  name: string;
  report_date: string; // YYYY-MM-DD
  fiscal_date_ending: string; // YYYY-MM-DD
  estimate: string;
  currency: string;
  rescheduled_to: string | null;
}

export interface ReportsResponse {
  updated_at: string | null;
  reports: Report[];
}

export interface WatchlistItem {
  symbol: string;
  name: string;
}

export interface WatchlistResponse {
  items: WatchlistItem[];
  refiltered?: boolean;
}

export interface JobStatusResponse {
  running: boolean;
  trigger: string | null;
  last_run_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  event_count: number | null;
  matched_symbols: string[];
  missing_symbols: string[];
  next_run_at: string | null;
  cooldown_until: string | null;
  updated_at: string | null;
}

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    let errorMessage = `HTTP ${res.status}: ${res.statusText}`;
    let data: unknown;
    try {
      data = await res.json();
      if (typeof data === "object" && data !== null && "detail" in data) {
        errorMessage = String((data as { detail: unknown }).detail);
      }
    } catch {
      // not JSON
    }
    throw new ApiError(res.status, errorMessage, data);
  }

  return res.json() as Promise<T>;
}

export async function fetchReports(params?: {
  start?: string;
  end?: string;
  symbols?: string[];
}): Promise<ReportsResponse> {
  const query = new URLSearchParams();
  if (params?.start) query.set("start", params.start);
  if (params?.end) query.set("end", params.end);
  if (params?.symbols) {
    for (const sym of params.symbols) {
      query.append("symbol", sym);
    }
  }

  const qs = query.toString();
  return request<ReportsResponse>(`/api/reports${qs ? `?${qs}` : ""}`);
}

export async function fetchWatchlist(): Promise<WatchlistResponse> {
  return request<WatchlistResponse>("/api/watchlist");
}

export async function addWatchlistItem(
  item: WatchlistItem,
): Promise<WatchlistResponse> {
  return request<WatchlistResponse>("/api/watchlist", {
    method: "POST",
    body: JSON.stringify(item),
  });
}

export async function removeWatchlistItem(
  symbol: string,
): Promise<WatchlistResponse> {
  return request<WatchlistResponse>(
    `/api/watchlist/${encodeURIComponent(symbol)}`,
    {
      method: "DELETE",
    },
  );
}

export async function fetchJobStatus(): Promise<JobStatusResponse> {
  return request<JobStatusResponse>("/api/jobs/status");
}

export async function triggerRefresh(): Promise<JobStatusResponse> {
  return request<JobStatusResponse>("/api/jobs/refresh", {
    method: "POST",
  });
}

export function getCalendarIcsUrl(): string {
  return "/api/calendar.ics";
}
