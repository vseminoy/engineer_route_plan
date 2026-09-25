"""Builds `data/geocache.csv` from the addresses of the source ticket files.

Run from `back/`: `python -m scripts.build_geocache` (or `make geocache` from the root).
Addresses already in the cache are not requested again; addresses in a remote town of
the Moscow region are not stored at all, they take the town's point from
`data/regions.toml`. Addresses Nominatim does not
find are listed and not written: their points are set by hand. The exit code is not 0
while any address of the sources is missing from the cache.
"""

import argparse
import asyncio
import csv
import sys
from pathlib import Path

import httpx

from src.clients.nominatim import NominatimClient
from src.domain import Point
from src.errors import DependencyUnavailable
from src.service.geocoding import cache_key, nominatim_queries, remote_town
from src.service.regions import Regions
from src.service.ticket_file import COL_ADDRESS, COL_DISTRICT, read_rows, split_rows

DEFAULT_SOURCES = (Path("../docs/synthetic_data"), Path("../docs/control_distribution"))
DEFAULT_CACHE = Path("data/geocache.csv")
DEFAULT_REGIONS = Path("data/regions.toml")
DEFAULT_URL = "https://nominatim.openstreetmap.org"
USER_AGENT = "engineer-route-plan/0.1 (geocache build)"


def source_addresses(sources: list[Path]) -> dict[str, tuple[str, str | None]]:
    """`cache_key` → (address, district) of every ticket and office address."""
    found: dict[str, tuple[str, str | None]] = {}
    for directory in sources:
        for path in sorted(directory.glob("*.csv")):
            split = split_rows(read_rows(path.read_bytes(), "csv"))
            if split.office_address:
                found.setdefault(cache_key(split.office_address), (split.office_address, None))
            for row in split.rows:
                address = row.values.get(COL_ADDRESS, "")
                if address:
                    district = row.values.get(COL_DISTRICT) or None
                    found.setdefault(cache_key(address), (address, district))
    return found


def read_cache(path: Path) -> dict[str, tuple[str, str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        return {cache_key(r[0]): (r[0], r[1], r[2]) for r in csv.reader(f, delimiter=";")}


def write_cache(path: Path, entries: dict[str, tuple[str, str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";", lineterminator="\n")
        for key in sorted(entries):
            writer.writerow(entries[key])


async def build(
    sources: list[Path], cache_path: Path, client: NominatimClient, towns: list[str]
) -> list[str]:
    """Adds the missing addresses to the cache file; returns those not found."""
    entries = read_cache(cache_path)
    by_query: dict[str, Point | None] = {}
    not_found = []
    refused = False
    for key, (address, district) in source_addresses(sources).items():
        if remote_town(address, district, towns):
            entries.pop(key, None)
            continue
        if key in entries:
            continue
        if refused:
            not_found.append(address)
            continue
        point = None
        try:
            for query in nominatim_queries(address):
                if query not in by_query:
                    by_query[query] = await client.search(query)
                point = by_query[query]
                if point is not None:
                    break
        except DependencyUnavailable:
            # Refused (403/429) or unreachable: every further request would fail the same
            # way, and the public service bans clients that keep trying.
            not_found.append(address)
            refused = True
            continue
        if point is None:
            not_found.append(address)
        else:
            entries[key] = (address, f"{point.lat:.7f}", f"{point.lon:.7f}")
    write_cache(cache_path, entries)
    return not_found


async def _main(args: argparse.Namespace) -> int:
    async with httpx.AsyncClient(
        base_url=args.url, headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(20.0)
    ) as http:
        towns = list(Regions.from_file(args.regions).remote_towns)
        not_found = await build(args.sources, args.cache, NominatimClient(http), towns)
    total = len(read_cache(args.cache))
    print(f"в кэше {total} адресов; не найдено {len(not_found)}")
    for address in not_found:
        print(f"  не найден: {address}")
    return 1 if not_found else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, nargs="+", default=list(DEFAULT_SOURCES))
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--regions", type=Path, default=DEFAULT_REGIONS)
    parser.add_argument("--url", default=DEFAULT_URL)
    sys.exit(asyncio.run(_main(parser.parse_args())))


if __name__ == "__main__":
    main()
