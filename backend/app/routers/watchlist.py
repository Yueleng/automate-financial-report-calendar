"""Watchlist CRUD; every change re-filters events from the cached raw CSV."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..core import Company
from ..deps import get_refresh, get_store
from ..jobs import RefreshService
from ..schemas import WatchlistItem, WatchlistResponse
from ..store import ReportStore

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

Store = Annotated[ReportStore, Depends(get_store)]
Refresh = Annotated[RefreshService, Depends(get_refresh)]


def _items(store: ReportStore) -> list[WatchlistItem]:
    return [WatchlistItem(symbol=c.symbol, name=c.name) for c in store.read_watchlist().values()]


def _save(store: ReportStore, refresh: RefreshService, companies: list[Company]) -> WatchlistResponse:
    if not companies:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The watchlist must keep at least one symbol.")
    with store.lock:
        store.write_watchlist(companies)
        refiltered = refresh.refilter()
    return WatchlistResponse(items=_items(store), refiltered=refiltered)


@router.get("", response_model=WatchlistResponse)
def get_watchlist(store: Store) -> WatchlistResponse:
    return WatchlistResponse(items=_items(store))


@router.post("", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
def add_symbol(item: WatchlistItem, store: Store, refresh: Refresh) -> WatchlistResponse:
    with store.lock:
        companies = store.read_watchlist()
        if item.symbol in companies:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{item.symbol} is already on the watchlist.")
        updated = [*companies.values(), Company(symbol=item.symbol, name=item.name or item.symbol)]
        return _save(store, refresh, updated)


@router.put("", response_model=WatchlistResponse)
def replace_watchlist(items: list[WatchlistItem], store: Store, refresh: Refresh) -> WatchlistResponse:
    unique: dict[str, Company] = {}
    for item in items:
        unique[item.symbol] = Company(symbol=item.symbol, name=item.name or item.symbol)
    return _save(store, refresh, list(unique.values()))


@router.delete("/{symbol}", response_model=WatchlistResponse)
def remove_symbol(symbol: str, store: Store, refresh: Refresh) -> WatchlistResponse:
    symbol = symbol.strip().upper()
    with store.lock:
        companies = store.read_watchlist()
        if symbol not in companies:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{symbol} is not on the watchlist.")
        return _save(store, refresh, [c for s, c in companies.items() if s != symbol])
