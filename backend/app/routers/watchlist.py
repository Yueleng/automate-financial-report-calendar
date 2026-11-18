"""Watchlist CRUD (Postgres); every change re-syncs events from the cached raw snapshot."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain import Company
from ..jobs import refilter
from ..repositories import WatchlistRepo
from ..schemas import WatchlistItem, WatchlistResponse

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

DbSession = Annotated[Session, Depends(get_session)]


def _items(repo: WatchlistRepo) -> list[WatchlistItem]:
    return [WatchlistItem(symbol=c.symbol, name=c.name) for c in repo.read().values()]


@router.get("", response_model=WatchlistResponse)
def get_watchlist(session: DbSession) -> WatchlistResponse:
    return WatchlistResponse(items=_items(WatchlistRepo(session)))


@router.post("", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
def add_symbol(item: WatchlistItem, session: DbSession) -> WatchlistResponse:
    repo = WatchlistRepo(session)
    if item.symbol in repo.read():
        raise HTTPException(status.HTTP_409_CONFLICT, f"{item.symbol} is already on the watchlist.")
    repo.add(Company(symbol=item.symbol, name=item.name or item.symbol))
    return WatchlistResponse(items=_items(repo), refiltered=refilter(session))


@router.put("", response_model=WatchlistResponse)
def replace_watchlist(items: list[WatchlistItem], session: DbSession) -> WatchlistResponse:
    if not items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Watchlist must contain at least one symbol.")
    unique: dict[str, Company] = {}
    for item in items:
        unique[item.symbol] = Company(symbol=item.symbol, name=item.name or item.symbol)
    repo = WatchlistRepo(session)
    repo.replace(list(unique.values()))
    return WatchlistResponse(items=_items(repo), refiltered=refilter(session))


@router.delete("/{symbol}", response_model=WatchlistResponse)
def remove_symbol(symbol: str, session: DbSession) -> WatchlistResponse:
    symbol = symbol.strip().upper()
    repo = WatchlistRepo(session)
    if symbol not in repo.read():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{symbol} is not on the watchlist.")
    repo.remove(symbol)
    return WatchlistResponse(items=_items(repo), refiltered=refilter(session))
