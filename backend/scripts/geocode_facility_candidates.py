#!/usr/bin/env python3
"""
Geocode the facility-candidate address list against a REAL geocoding
provider (Nominatim by default) and write the results to a separate
candidate file. This script never modifies app/data/demo/demo_facilities.json.

Why this exists: app/data/demo/demo_facilities.json currently stores 18
facilities along the Chandigarh-Ludhiana (NH-95) corridor whose coordinates
are manual, address-derived ESTIMATES (verification_status =
"unverified_coordinates", coordinate_source = "address-derived-approximation").
This script attempts to replace that manual estimate with a real geocoder
match for each facility's existing `address` field, producing a candidate
record a human can review before it is ever promoted into the live demo
data.

Geocoding vs. verification (read before using this script's output):
  A successful geocoding match means Nominatim matched the given address
  text to a geographic location. It does NOT mean:
    - the business currently exists at that location
    - the business is open or operating
    - the phone number, hours, or listed services are accurate
    - a human has physically inspected the site
  Accordingly, a successful match here is recorded as verification_status
  "address_matched" - one of the FacilityVerificationStatus values already
  defined in app/schemas/facility.py - never "verified". "verified" is
  reserved (per that schema's own docstring) for coordinates returned
  directly by an authoritative source such as an OSM/Overpass node, which
  this script does not do.

Output (both under app/data/demo/, both gitignored-candidate files, neither
is read by the running application):
  geocoded_facility_candidates.json
      One entry per facility that was successfully geocoded. Each entry
      keeps the original source record (name/category/address/original_id)
      alongside the new coordinates, geocoding source, and timestamp, so
      the result stays traceable back to demo_facilities.json.
  geocoding_failures.json
      One entry per facility that could NOT be geocoded, with the reason
      (timeout, HTTP error, malformed response, no match, etc.) and the
      original record, for manual review. Coordinates are never fabricated
      for these.

Rerunning this script is safe: results are merged and keyed by
`original_id`, so a second run updates existing entries in place instead
of appending duplicates.

Crash / interruption safety:
  Output is checkpointed to disk after EACH candidate is processed, not
  only once at the end. If the script is interrupted (Ctrl-C, crash,
  network loss) partway through, every candidate already written before
  the interruption is preserved; only the still-unprocessed candidates
  need to be retried on the next run (which happens automatically, since
  reruns merge by original_id).

  Every write (checkpoint or final) goes to a temporary file in the same
  directory first, then is atomically renamed onto the real target via
  os.replace(). This means a write that is itself interrupted mid-flight
  cannot leave a half-written or corrupted output file, and cannot destroy
  previously-good content: the old file stays intact until the new one is
  fully written and the rename succeeds.

  If an existing output file contains invalid JSON (for example from manual
  editing or external corruption), the script reports exactly which file
  and the parse error, then stops BEFORE processing or writing anything -
  it never overwrites or discards a file it could not safely read.

This script requires real outbound network access to the configured
geocoding provider (Nominatim's public instance by default). It could NOT
be run successfully in the sandboxed environment this task was performed
in - see the review report for details. Run it yourself wherever you have
real internet access to nominatim.openstreetmap.org.

Usage:
    cd backend
    python3 scripts/geocode_facility_candidates.py
    python3 scripts/geocode_facility_candidates.py --source app/data/demo/demo_facilities.json
    python3 scripts/geocode_facility_candidates.py --only demo-fuel-001 demo-hospital-003
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.exceptions import (  # noqa: E402
    NotFoundError,
    ServiceError,
    ServiceResponseError,
    ServiceUnavailableError,
)
from app.services.routing import RoutingService  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "demo"
DEFAULT_SOURCE_PATH = DATA_DIR / "demo_facilities.json"
CANDIDATES_PATH = DATA_DIR / "geocoded_facility_candidates.json"
FAILURES_PATH = DATA_DIR / "geocoding_failures.json"

GEOCODING_SOURCE_LABEL = "nominatim-geocoded"


class CorruptedOutputError(Exception):
    """Raised when an existing output file (candidates or failures) exists
    but cannot be parsed as a JSON array. The script must stop before doing
    any work - it must never overwrite or discard a file it could not
    safely read, since the corruption might be the only copy of real data
    (e.g. a human mid-edit, or disk/transfer corruption)."""

    def __init__(self, path: Path, original_error: Exception):
        self.path = path
        self.original_error = original_error
        super().__init__(
            f"Existing output file is not valid JSON and will NOT be touched: "
            f"{path}\n"
            f"Parse error: {original_error}\n"
            f"Fix or remove this file manually, then rerun. Nothing was "
            f"overwritten or discarded."
        )


def _load_json_list(path: Path) -> List[dict]:
    """Load a JSON array from path. Returns [] if the file does not exist
    yet (first run). Raises CorruptedOutputError - with the exact file and
    parse error - if the file exists but is not valid JSON, rather than
    letting a raw JSONDecodeError propagate or silently treating corrupt
    content as empty."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        raw_text = fh.read()
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise CorruptedOutputError(path, exc) from exc
    if not isinstance(data, list):
        raise CorruptedOutputError(
            path, ValueError(f"expected a JSON array, found {type(data).__name__}")
        )
    return data


def _atomic_write_json(path: Path, records: List[dict]) -> None:
    """Write `records` to path as pretty-printed JSON, atomically.

    Writes to a temporary file in the same directory first (so the rename
    below is on the same filesystem and therefore atomic on POSIX), flushes
    and fsyncs it to disk, then renames it onto the real target with
    os.replace(). os.replace() either fully succeeds or leaves the
    original target file completely untouched - there is no intermediate
    state where `path` is partially written or missing. This guarantees a
    failed/interrupted write cannot destroy or corrupt the previous valid
    output.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = _mkstemp_in(path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(records, indent=2))
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)  # atomic on POSIX; all-or-nothing
    except BaseException:
        # Clean up the temp file on any failure (including KeyboardInterrupt
        # during the write) so no stray .tmp files are left behind. The
        # real target `path` is never touched unless os.replace() above
        # already completed successfully.
        tmp_path.unlink(missing_ok=True)
        raise


def _mkstemp_in(directory: Path, prefix: str, suffix: str):
    import tempfile

    return tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=str(directory))


def _load_source_candidates(path: Path, only_ids: Optional[List[str]]) -> List[dict]:
    """Read the candidate source list. This file is read-only here - this
    script never writes back to it."""
    raw = _load_json_list(path)
    candidates = []
    for item in raw:
        clean = {k: v for k, v in item.items() if not k.startswith("_")}
        candidates.append(clean)
    if only_ids:
        wanted = set(only_ids)
        candidates = [c for c in candidates if c.get("id") in wanted]
        missing = wanted - {c.get("id") for c in candidates}
        if missing:
            print(
                f"Warning: requested id(s) not found in {path}: {sorted(missing)}",
                file=sys.stderr,
            )
    return candidates


def _index_by_original_id(records: List[dict]) -> Dict[str, dict]:
    return {r["original_id"]: r for r in records if r.get("original_id")}


async def _geocode_one(
    routing: RoutingService, candidate: dict, geocoding_provider_url: str
) -> "tuple[Optional[dict], Optional[dict]]":
    """Returns (candidate_record, failure_record) - exactly one is not None."""
    original_id = candidate.get("id")
    name = candidate.get("name")
    address = candidate.get("address")
    category = candidate.get("category")

    retrieved_at = datetime.now(timezone.utc).isoformat()

    if not address:
        return None, {
            "original_id": original_id,
            "name": name,
            "category": category,
            "address": address,
            "failure_reason": "missing_address",
            "detail": "Source record has no address field to geocode.",
            "attempted_at": retrieved_at,
        }

    try:
        result = await routing.geocode(address)
    except NotFoundError as exc:
        return None, {
            "original_id": original_id,
            "name": name,
            "category": category,
            "address": address,
            "failure_reason": "no_match",
            "detail": exc.message,
            "attempted_at": retrieved_at,
        }
    except ServiceResponseError as exc:
        return None, {
            "original_id": original_id,
            "name": name,
            "category": category,
            "address": address,
            "failure_reason": "invalid_response",
            "detail": exc.message,
            "attempted_at": retrieved_at,
        }
    except ServiceUnavailableError as exc:
        return None, {
            "original_id": original_id,
            "name": name,
            "category": category,
            "address": address,
            "failure_reason": exc.reason,
            "detail": exc.message,
            "attempted_at": retrieved_at,
        }
    except ServiceError as exc:
        return None, {
            "original_id": original_id,
            "name": name,
            "category": category,
            "address": address,
            "failure_reason": "error",
            "detail": exc.message,
            "attempted_at": retrieved_at,
        }

    lat = result.coordinates.lat
    lon = result.coordinates.lon
    warnings: List[str] = []
    # Defensive re-check even though Coordinates() already validates range -
    # this makes an out-of-range value a recorded warning on the candidate
    # rather than a silent pass-through, in case that validation ever changes.
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        warnings.append("coordinates_out_of_valid_range")

    candidate_record = {
        "original_id": original_id,
        "name": name,
        "category": category,
        "address": address,
        "coordinates": {"lat": lat, "lon": lon},
        "geocoding_display_name": result.display_name,
        "source": "demo-deepak-directory",
        "verification_status": "address_matched",
        "coordinate_source": GEOCODING_SOURCE_LABEL,
        "geocoding_provider_url": geocoding_provider_url,
        "last_verified_at": retrieved_at,
        "warnings": warnings,
    }
    return candidate_record, None


async def main(source_path: Path, only_ids: Optional[List[str]]) -> int:
    settings = get_settings()
    if not settings.geocoding_configured:
        print(
            "Geocoding provider is not configured (GEOCODING_PROVIDER_URL is empty). "
            "Nothing to do.",
            file=sys.stderr,
        )
        return 1

    candidates = _load_source_candidates(source_path, only_ids)
    if not candidates:
        print(f"No candidate records found in {source_path}.", file=sys.stderr)
        return 1

    print(f"Loaded {len(candidates)} candidate record(s) from {source_path}")
    # Never print full Settings() - it is a superset that could grow to
    # include a provider key field in future; print only the non-secret
    # URL this run actually uses.
    print(f"Geocoding provider: {settings.GEOCODING_PROVIDER_URL}")
    print(
        f"Throttle: {settings.NOMINATIM_MIN_INTERVAL_SECONDS}s minimum between requests\n"
    )

    # Load any existing output BEFORE doing any work or any writing. If
    # either file exists but is corrupted, this raises CorruptedOutputError
    # and main() aborts here - nothing has been processed and nothing has
    # been written, so the corrupted file is left exactly as it was.
    try:
        existing_candidates = _index_by_original_id(_load_json_list(CANDIDATES_PATH))
        existing_failures = _index_by_original_id(_load_json_list(FAILURES_PATH))
    except CorruptedOutputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    def _checkpoint() -> None:
        """Persist current progress atomically. Called after every single
        candidate (success or failure) so an interruption anywhere in the
        loop loses at most the one candidate in flight, never anything
        already processed."""
        candidates_out = sorted(
            existing_candidates.values(), key=lambda r: r["original_id"] or ""
        )
        failures_out = sorted(
            existing_failures.values(), key=lambda r: r["original_id"] or ""
        )
        _atomic_write_json(CANDIDATES_PATH, candidates_out)
        _atomic_write_json(FAILURES_PATH, failures_out)
        return candidates_out, failures_out

    async with httpx.AsyncClient(
        timeout=settings.REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": settings.HTTP_USER_AGENT},
    ) as http_client:
        routing = RoutingService(settings=settings, client=http_client)
        succeeded = 0
        failed = 0
        candidates_out: List[dict] = []
        failures_out: List[dict] = []
        try:
            for i, candidate in enumerate(candidates, start=1):
                label = candidate.get("name") or candidate.get("id") or "?"
                print(f"[{i}/{len(candidates)}] Geocoding {label!r}...")
                record, failure = await _geocode_one(
                    routing, candidate, settings.GEOCODING_PROVIDER_URL
                )
                if record is not None:
                    existing_candidates[record["original_id"]] = record
                    # A previously-recorded failure for this id is now
                    # resolved - remove it so stale failures don't linger.
                    existing_failures.pop(record["original_id"], None)
                    succeeded += 1
                    print(
                        f"    -> matched ({record['coordinates']['lat']}, "
                        f"{record['coordinates']['lon']}): "
                        f"{record['geocoding_display_name']}"
                    )
                else:
                    existing_failures[failure["original_id"]] = failure
                    failed += 1
                    print(
                        f"    -> FAILED ({failure['failure_reason']}): {failure['detail']}"
                    )
                # Checkpoint after this candidate, win or lose, before
                # moving on to the next one.
                candidates_out, failures_out = _checkpoint()
        finally:
            await routing.aclose()

    print(f"\nThis run: {succeeded} succeeded, {failed} failed.")
    print(f"Candidate file now has {len(candidates_out)} total record(s): {CANDIDATES_PATH}")
    print(f"Failure file now has {len(failures_out)} total record(s): {FAILURES_PATH}")
    print(
        "\nNOTE: app/data/demo/demo_facilities.json was NOT modified by this script. "
        "Review the candidate file before deciding whether/how to merge any "
        "of its entries into the live demo data."
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_PATH,
        help="Path to the JSON array of candidate facilities to geocode "
        "(default: app/data/demo/demo_facilities.json, read-only).",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        metavar="ID",
        help="Only process candidates whose 'id' is in this list.",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.source, args.only)))
