"""Coordinates of addresses: the static geocache first, Nominatim only for the rest."""

import csv
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from src.domain import Point
from src.logging import get_logger

logger = get_logger(__name__)


_STREET_TYPES = {
    "ул": "улица",
    "пр-кт": "проспект",
    "проезд": "проезд",
    "пр-зд": "проезд",
    "пер": "переулок",
    "б-р": "бульвар",
    "наб": "набережная",
    "ш": "шоссе",
    "пл": "площадь",
    "туп": "тупик",
}
# Everything from the apartment, entrance, floor or office on: it identifies a person and
# does not help to find the house. The marker follows a space, a comma or, glued, a house
# number ("д.5кв.12"); a hyphen after it means a word such as "кв-л" (block).
_APARTMENT = re.compile(
    r"(?:[\s,]|(?<=\d))(?:кв|квартира|подъезд|под|этаж|эт|оф|офис)(?![а-яё-])", re.IGNORECASE
)
# "д. 128 к 5", "д 83с 4", "д. 24/30 стр. 1", "д. 6к1": everything after "д" up to a comma.
_HOUSE = re.compile(r"(?:^|[\s,])д\.?\s?(\d[^,]*)")
_MOSCOW = re.compile(r"^(?:г\.\s?)?(?:Город\s)?Москва\b[\s,]*", re.IGNORECASE)
_STREET_PREFIX = re.compile(r"([а-яё-]+)(?:\.\s?|\s)", re.IGNORECASE)


def cache_key(address: str) -> str:
    return " ".join(address.split()).casefold()


def remote_town(address: str, district: str | None, towns: Iterable[str]) -> str | None:
    """The remote town of the Moscow region the address is in, by district or by name."""
    for town in towns:
        if district == town or re.search(rf"\b{re.escape(town)}\b", address):
            return town
    return None


def _street(text: str) -> tuple[str, str]:
    """(name, spelled-out type) of "ул.Земляной Вал", "ул Юных Ленинцев" or
    "Бирюлевская ул."; the type is empty when there is none."""
    prefix = _STREET_PREFIX.match(text)
    if prefix and prefix.group(1).lower() in _STREET_TYPES:
        return text[prefix.end() :].strip(), _STREET_TYPES[prefix.group(1).lower()]
    head, _, last = text.rpartition(" ")
    if head and last.rstrip(".").lower() in _STREET_TYPES:
        return head.strip(), _STREET_TYPES[last.rstrip(".").lower()]
    return text, ""


def nominatim_queries(address: str) -> list[str]:
    """Free-form Nominatim queries to try in order: the apartment dropped, street types
    spelled out, the house written as OpenStreetMap does ("128к5", "24/30с1"); then the
    street type before the name, and between an ordinal and the name ("2-я улица
    Синичкина"); then the house without its block or building number.

    Whitespace is collapsed first and no pattern backtracks over a run of it, so the
    time stays linear in the length of the address."""
    text = " ".join(address.split())
    apartment = _APARTMENT.search(text)
    if apartment:
        text = text[: apartment.start()]
    text = re.sub(r"^г\.\s?(?=Город)", "", text)
    text = _MOSCOW.sub("", text).strip(" ,")
    house = ""
    m = _HOUSE.search(text)
    if m:
        house = re.sub(r"стр\.?", "с", m.group(1))
        house = re.sub(r"[\s.]", "", house)
        text = text[: m.start()]
    name, kind = _street(text.strip(" ,."))
    base = re.match(r"[\d/]+(?:[а-яА-Я](?!\d))?", house)
    houses = [house] + ([base.group(0)] if base and base.group(0) != house else [])
    queries = [f"{name} {kind} {house}", f"{kind} {name} {house}"]
    ordinal = re.match(r"(\d+-[яйе]) (.+)", name)
    if ordinal:
        queries.append(f"{ordinal.group(1)} {kind} {ordinal.group(2)} {house}")
    queries += [f"{kind} {name} {h}" for h in houses[1:]]
    return list(dict.fromkeys(" ".join(q.split()) + ", Москва" for q in queries))


class PlaceSearch(Protocol):
    """An external geocoder: the best match for a free-form query, or `None`."""

    async def search(self, query: str) -> Point | None: ...


class GeoCache:
    """`address;lat;lon`, UTF-8; addresses are matched ignoring case and extra spaces."""

    def __init__(self, points: dict[str, Point]) -> None:
        self._points = {cache_key(a): p for a, p in points.items()}

    @classmethod
    def from_file(cls, path: Path) -> "GeoCache":
        points = {}
        with path.open(encoding="utf-8", newline="") as f:
            for address, lat, lon in csv.reader(f, delimiter=";"):
                points[address] = Point(lat=float(lat), lon=float(lon))
        return cls(points)

    def get(self, address: str) -> Point | None:
        return self._points.get(cache_key(address))


class Geocoder:
    """Addresses in a remote town of the Moscow region get the town's configured point,
    not a street-level one: those towns are served as one place.

    At most `max_lookups` cache misses of one `locate` call go to Nominatim; each may
    take several queries at one per second, and the public service forbids bulk
    geocoding. The misses beyond it stay without a point."""

    def __init__(
        self,
        cache: GeoCache,
        client: PlaceSearch | None,
        towns: dict[str, Point],
        max_lookups: int,
    ) -> None:
        self._cache = cache
        self._client = client
        self._towns = towns
        self._max_lookups = max_lookups

    async def locate(self, addresses: Iterable[tuple[str, str | None]]) -> dict[str, Point]:
        """Points of `(address, district)` pairs keyed by `cache_key(address)`; an address
        found nowhere is absent. `DependencyUnavailable` from Nominatim propagates."""
        found: dict[str, Point] = {}
        misses: dict[str, tuple[str, str | None]] = {}
        for address, district in addresses:
            key = cache_key(address)
            town = remote_town(address, district, self._towns)
            point = self._towns[town] if town else self._cache.get(address)
            if point is not None:
                found[key] = point
            else:
                misses.setdefault(key, (address, district))
        if not misses:
            return found
        looked_up = min(len(misses), self._max_lookups) if self._client else 0
        logger.info(
            "geocode_cache_miss", misses=len(misses), lookups_skipped=len(misses) - looked_up
        )
        if self._client is None:
            return found
        for key, (address, _district) in list(misses.items())[:looked_up]:
            for query in nominatim_queries(address):
                point = await self._client.search(query)
                if point is not None:
                    found[key] = point
                    break
        return found
