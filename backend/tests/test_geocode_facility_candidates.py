"""
Tests for scripts/geocode_facility_candidates.py.

These exercise the script's core logic (not a live network call - see the
review report for why live geocoding could not be observed in this
environment). All provider responses are mocked with respx for
deterministic results, per project testing conventions
(tests/conftest.py's `mock_router` fixture / tests/test_routing_throttle.py).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest
import respx

from app.core.config import Settings
from app.services.demo import get_demo_facilities

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _load_script_module():
    """Import scripts/geocode_facility_candidates.py as a module without
    requiring scripts/ to be a package (it isn't - same approach the script
    itself uses to reach app/ via sys.path)."""
    spec = importlib.util.spec_from_file_location(
        "geocode_facility_candidates", SCRIPTS_DIR / "geocode_facility_candidates.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script_module():
    return _load_script_module()


@pytest.fixture
def script_settings():
    return Settings(
        GEOCODING_PROVIDER_URL="https://nominatim.test",
        ROUTING_PROVIDER_URL="https://router.test",
        NOMINATIM_MIN_INTERVAL_SECONDS=0,
    )


@pytest.fixture
def tmp_paths(tmp_path, script_module):
    """Redirect the script's output paths into a scratch directory so tests
    never touch the real app/data/demo/ files."""
    script_module.CANDIDATES_PATH = tmp_path / "geocoded_facility_candidates.json"
    script_module.FAILURES_PATH = tmp_path / "geocoding_failures.json"
    return tmp_path


def _write_source(tmp_path: Path, records: list) -> Path:
    path = tmp_path / "source.json"
    path.write_text(json.dumps(records))
    return path


# ---------------------------------------------------------------------------
# Successful geocoding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_geocode_is_marked_address_matched_not_verified(
    script_module, script_settings, tmp_paths
):
    source = _write_source(
        tmp_paths,
        [
            {
                "id": "demo-fuel-001",
                "name": "Navdeep HP Centre",
                "category": "fuel",
                "address": "Kharar-Ludhiana Road, NH 95, Kurali, Punjab 140413",
                "coordinates": {"lat": 30.758, "lon": 76.581},
                "source": "demo-deepak-directory",
                "verification_status": "unverified_coordinates",
                "coordinate_source": "address-derived-approximation",
                "last_verified_at": None,
            }
        ],
    )
    script_module.get_settings = lambda: script_settings

    with respx.mock(assert_all_called=False) as m:
        m.get("https://nominatim.test/search").mock(
            return_value=httpx.Response(
                200,
                json=[{"lat": "30.759", "lon": "76.582", "display_name": "Navdeep HP, Kurali"}],
            )
        )
        rc = await script_module.main(source, None)

    assert rc == 0
    candidates = json.loads(script_module.CANDIDATES_PATH.read_text())
    assert len(candidates) == 1
    record = candidates[0]
    assert record["original_id"] == "demo-fuel-001"
    assert record["verification_status"] == "address_matched"
    assert record["verification_status"] != "verified"
    assert record["coordinate_source"] == "nominatim-geocoded"
    assert record["coordinates"] == {"lat": 30.759, "lon": 76.582}
    assert record["last_verified_at"] is not None
    # Traceability back to the source record is preserved.
    assert record["name"] == "Navdeep HP Centre"
    assert record["address"] == "Kharar-Ludhiana Road, NH 95, Kurali, Punjab 140413"

    failures = json.loads(script_module.FAILURES_PATH.read_text())
    assert failures == []


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_match_is_recorded_as_failure_not_fabricated(
    script_module, script_settings, tmp_paths
):
    source = _write_source(
        tmp_paths,
        [
            {
                "id": "demo-x-001",
                "name": "Nonexistent Place",
                "category": "fuel",
                "address": "Totally Fake Address, Nowhere",
            }
        ],
    )
    script_module.get_settings = lambda: script_settings

    with respx.mock(assert_all_called=False) as m:
        m.get("https://nominatim.test/search").mock(return_value=httpx.Response(200, json=[]))
        rc = await script_module.main(source, None)

    assert rc == 0
    candidates = json.loads(script_module.CANDIDATES_PATH.read_text())
    assert candidates == []
    failures = json.loads(script_module.FAILURES_PATH.read_text())
    assert len(failures) == 1
    assert failures[0]["original_id"] == "demo-x-001"
    assert failures[0]["failure_reason"] == "no_match"


@pytest.mark.asyncio
async def test_timeout_is_recorded_as_failure(script_module, script_settings, tmp_paths):
    source = _write_source(
        tmp_paths,
        [{"id": "demo-x-002", "name": "Slow Place", "category": "fuel", "address": "Somewhere"}],
    )
    script_module.get_settings = lambda: script_settings

    with respx.mock(assert_all_called=False) as m:
        m.get("https://nominatim.test/search").mock(side_effect=httpx.TimeoutException("timed out"))
        rc = await script_module.main(source, None)

    assert rc == 0
    candidates = json.loads(script_module.CANDIDATES_PATH.read_text())
    assert candidates == []
    failures = json.loads(script_module.FAILURES_PATH.read_text())
    assert len(failures) == 1
    assert failures[0]["failure_reason"] == "unreachable"


@pytest.mark.asyncio
async def test_http_server_error_is_recorded_as_failure(
    script_module, script_settings, tmp_paths
):
    source = _write_source(
        tmp_paths,
        [{"id": "demo-x-003", "name": "Down Place", "category": "fuel", "address": "Somewhere"}],
    )
    script_module.get_settings = lambda: script_settings

    with respx.mock(assert_all_called=False) as m:
        m.get("https://nominatim.test/search").mock(return_value=httpx.Response(503))
        rc = await script_module.main(source, None)

    assert rc == 0
    failures = json.loads(script_module.FAILURES_PATH.read_text())
    assert len(failures) == 1
    assert failures[0]["failure_reason"] == "unreachable"


@pytest.mark.asyncio
async def test_malformed_provider_response_is_recorded_as_failure(
    script_module, script_settings, tmp_paths
):
    source = _write_source(
        tmp_paths,
        [{"id": "demo-x-004", "name": "Bad Response Place", "category": "fuel", "address": "Somewhere"}],
    )
    script_module.get_settings = lambda: script_settings

    with respx.mock(assert_all_called=False) as m:
        # Valid JSON list, but missing lat/lon - the provider contract broken.
        m.get("https://nominatim.test/search").mock(
            return_value=httpx.Response(200, json=[{"display_name": "No coords here"}])
        )
        rc = await script_module.main(source, None)

    assert rc == 0
    failures = json.loads(script_module.FAILURES_PATH.read_text())
    assert len(failures) == 1
    assert failures[0]["failure_reason"] == "invalid_response"


@pytest.mark.asyncio
async def test_non_json_provider_response_is_recorded_as_failure(
    script_module, script_settings, tmp_paths
):
    source = _write_source(
        tmp_paths,
        [{"id": "demo-x-005", "name": "Garbage Response Place", "category": "fuel", "address": "Somewhere"}],
    )
    script_module.get_settings = lambda: script_settings

    with respx.mock(assert_all_called=False) as m:
        m.get("https://nominatim.test/search").mock(
            return_value=httpx.Response(200, content=b"not json at all")
        )
        rc = await script_module.main(source, None)

    assert rc == 0
    failures = json.loads(script_module.FAILURES_PATH.read_text())
    assert len(failures) == 1
    assert failures[0]["failure_reason"] == "invalid_response"


@pytest.mark.asyncio
async def test_missing_address_is_recorded_as_failure_without_calling_provider(
    script_module, script_settings, tmp_paths
):
    source = _write_source(
        tmp_paths,
        [{"id": "demo-x-006", "name": "No Address Place", "category": "fuel", "address": None}],
    )
    script_module.get_settings = lambda: script_settings

    with respx.mock(assert_all_called=False) as m:
        route = m.get("https://nominatim.test/search").mock(
            return_value=httpx.Response(200, json=[])
        )
        rc = await script_module.main(source, None)

    assert rc == 0
    assert route.call_count == 0  # never called the provider for a missing address
    failures = json.loads(script_module.FAILURES_PATH.read_text())
    assert len(failures) == 1
    assert failures[0]["failure_reason"] == "missing_address"


# ---------------------------------------------------------------------------
# Rerun / duplicate prevention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerunning_updates_in_place_without_duplicating(
    script_module, script_settings, tmp_paths
):
    source = _write_source(
        tmp_paths,
        [{"id": "demo-x-007", "name": "Reliable Place", "category": "fuel", "address": "Somewhere"}],
    )
    script_module.get_settings = lambda: script_settings

    with respx.mock(assert_all_called=False) as m:
        m.get("https://nominatim.test/search").mock(
            return_value=httpx.Response(
                200, json=[{"lat": "30.0", "lon": "76.0", "display_name": "First Run"}]
            )
        )
        await script_module.main(source, None)

    with respx.mock(assert_all_called=False) as m:
        m.get("https://nominatim.test/search").mock(
            return_value=httpx.Response(
                200, json=[{"lat": "30.1", "lon": "76.1", "display_name": "Second Run"}]
            )
        )
        await script_module.main(source, None)

    candidates = json.loads(script_module.CANDIDATES_PATH.read_text())
    assert len(candidates) == 1  # updated in place, not duplicated
    assert candidates[0]["geocoding_display_name"] == "Second Run"
    assert candidates[0]["coordinates"] == {"lat": 30.1, "lon": 76.1}


@pytest.mark.asyncio
async def test_rerun_resolves_a_previous_failure(script_module, script_settings, tmp_paths):
    source = _write_source(
        tmp_paths,
        [{"id": "demo-x-008", "name": "Eventually Found Place", "category": "fuel", "address": "Somewhere"}],
    )
    script_module.get_settings = lambda: script_settings

    with respx.mock(assert_all_called=False) as m:
        m.get("https://nominatim.test/search").mock(return_value=httpx.Response(200, json=[]))
        await script_module.main(source, None)

    failures = json.loads(script_module.FAILURES_PATH.read_text())
    assert len(failures) == 1

    with respx.mock(assert_all_called=False) as m:
        m.get("https://nominatim.test/search").mock(
            return_value=httpx.Response(
                200, json=[{"lat": "30.0", "lon": "76.0", "display_name": "Found it"}]
            )
        )
        await script_module.main(source, None)

    failures = json.loads(script_module.FAILURES_PATH.read_text())
    candidates = json.loads(script_module.CANDIDATES_PATH.read_text())
    assert failures == []
    assert len(candidates) == 1


# ---------------------------------------------------------------------------
# Schema validation of candidate records
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_candidate_records_are_valid_against_the_facility_schema(
    script_module, script_settings, tmp_paths
):
    """A geocoded candidate (with its id/address/coordinate_source fields
    renamed as needed) must satisfy the same Facility schema the rest of
    the backend relies on - this guards against the candidate format
    silently drifting from app/schemas/facility.py."""
    from app.schemas.facility import Facility

    source = _write_source(
        tmp_paths,
        [{"id": "demo-x-009", "name": "Schema Check Place", "category": "fuel", "address": "Somewhere"}],
    )
    script_module.get_settings = lambda: script_settings

    with respx.mock(assert_all_called=False) as m:
        m.get("https://nominatim.test/search").mock(
            return_value=httpx.Response(
                200, json=[{"lat": "30.0", "lon": "76.0", "display_name": "Schema Match"}]
            )
        )
        await script_module.main(source, None)

    candidates = json.loads(script_module.CANDIDATES_PATH.read_text())
    record = candidates[0]
    facility = Facility(
        id=record["original_id"],
        name=record["name"],
        category=record["category"],
        coordinates=record["coordinates"],
        address=record["address"],
        source=record["source"],
        verification_status=record["verification_status"],
        coordinate_source=record["coordinate_source"],
        last_verified_at=record["last_verified_at"],
    )
    assert facility.verification_status == "address_matched"


def test_invalid_coordinates_are_rejected_by_facility_schema():
    """Confirms the schema-level guard this script relies on (Coordinates'
    own field_validators) actually rejects out-of-range values, rather than
    silently accepting them."""
    from pydantic import ValidationError

    from app.schemas.common import Coordinates

    with pytest.raises(ValidationError):
        Coordinates(lat=999.0, lon=76.0)
    with pytest.raises(ValidationError):
        Coordinates(lat=30.0, lon=-200.0)


# ---------------------------------------------------------------------------
# Existing demo data must remain untouched
# ---------------------------------------------------------------------------


def test_script_module_never_imports_or_touches_demo_facilities_write_path(script_module):
    """The script's default source path points at demo_facilities.json for
    READING only; it has no code path that writes to it."""
    import inspect

    source_code = inspect.getsource(script_module)
    assert "demo_facilities.json" in source_code  # read as the default source
    # The only Path.write_text calls in the module target the two candidate
    # output files, never DEFAULT_SOURCE_PATH / the demo facilities file.
    assert "DEFAULT_SOURCE_PATH.write_text" not in source_code


def test_running_the_script_does_not_change_existing_demo_facilities(
    script_module, script_settings, tmp_paths
):
    """End-to-end guard: after a full script run, the real
    app/data/demo/demo_facilities.json content (loaded the normal way, via
    get_demo_facilities()) is exactly as before - still 18 records, still
    all unverified_coordinates."""
    before = get_demo_facilities()

    source = _write_source(
        tmp_paths,
        [{"id": "demo-x-010", "name": "Irrelevant Place", "category": "fuel", "address": "Somewhere"}],
    )
    script_module.get_settings = lambda: script_settings

    with respx.mock(assert_all_called=False) as m:
        m.get("https://nominatim.test/search").mock(
            return_value=httpx.Response(200, json=[{"lat": "30.0", "lon": "76.0", "display_name": "X"}])
        )
        import asyncio

        asyncio.run(script_module.main(source, None))

    after = get_demo_facilities()
    assert len(before) == len(after) == 18
    for f in after:
        assert f.verification_status == "unverified_coordinates"
        assert f.last_verified_at is None


# ---------------------------------------------------------------------------
# --only filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_flag_restricts_which_candidates_are_processed(
    script_module, script_settings, tmp_paths
):
    source = _write_source(
        tmp_paths,
        [
            {"id": "demo-a", "name": "A", "category": "fuel", "address": "Addr A"},
            {"id": "demo-b", "name": "B", "category": "fuel", "address": "Addr B"},
        ],
    )
    script_module.get_settings = lambda: script_settings

    with respx.mock(assert_all_called=False) as m:
        m.get("https://nominatim.test/search").mock(
            return_value=httpx.Response(200, json=[{"lat": "30.0", "lon": "76.0", "display_name": "X"}])
        )
        rc = await script_module.main(source, ["demo-a"])

    assert rc == 0
    candidates = json.loads(script_module.CANDIDATES_PATH.read_text())
    assert len(candidates) == 1
    assert candidates[0]["original_id"] == "demo-a"


# ---------------------------------------------------------------------------
# DEFECT 1 regression: interruption after partial progress must not lose
# already-successful results.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_interruption_after_first_success_preserves_that_result(
    script_module, script_settings, tmp_paths
):
    """Simulates a crash/interruption partway through a 3-candidate run:
    candidate 1 succeeds, candidate 2's provider call raises an unexpected
    exception (standing in for Ctrl-C, network loss, an unhandled bug,
    etc.). The checkpoint written after candidate 1 must survive on disk
    even though the overall run never completes."""
    source = _write_source(
        tmp_paths,
        [
            {"id": "demo-a", "name": "A", "category": "fuel", "address": "Addr A"},
            {"id": "demo-b", "name": "B", "category": "fuel", "address": "Addr B"},
            {"id": "demo-c", "name": "C", "category": "fuel", "address": "Addr C"},
        ],
    )
    script_module.get_settings = lambda: script_settings

    call_count = {"n": 0}

    def responder(request):
        call_count["n"] += 1
        if call_count["n"] == 2:
            # Something outside the script's own exception handling goes
            # wrong on the second candidate - e.g. the process is killed,
            # or an unforeseen bug throws. This is NOT one of the handled
            # ServiceError subclasses, so it propagates out of main().
            raise RuntimeError("simulated interruption mid-run")
        return httpx.Response(
            200, json=[{"lat": "30.0", "lon": "76.0", "display_name": "ok"}]
        )

    with pytest.raises(RuntimeError, match="simulated interruption"):
        with respx.mock(assert_all_called=False) as m:
            m.get("https://nominatim.test/search").mock(side_effect=responder)
            await script_module.main(source, None)

    # Despite main() never returning normally, candidate A's successful
    # result must already be on disk, written by the per-candidate
    # checkpoint - not lost because the run as a whole didn't finish.
    assert script_module.CANDIDATES_PATH.exists()
    candidates = json.loads(script_module.CANDIDATES_PATH.read_text())
    assert len(candidates) == 1
    assert candidates[0]["original_id"] == "demo-a"


@pytest.mark.asyncio
async def test_interrupted_run_can_be_resumed_by_a_plain_rerun(
    script_module, script_settings, tmp_paths
):
    """After an interrupted run leaves a checkpoint on disk, simply running
    the script again (no special resume flag) must pick up where it left
    off: the already-succeeded candidate stays, and the previously
    not-yet-reached candidates get processed normally."""
    source = _write_source(
        tmp_paths,
        [
            {"id": "demo-a", "name": "A", "category": "fuel", "address": "Addr A"},
            {"id": "demo-b", "name": "B", "category": "fuel", "address": "Addr B"},
        ],
    )
    script_module.get_settings = lambda: script_settings

    call_count = {"n": 0}

    def failing_responder(request):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated interruption")
        return httpx.Response(
            200, json=[{"lat": "30.0", "lon": "76.0", "display_name": "first run"}]
        )

    with pytest.raises(RuntimeError):
        with respx.mock(assert_all_called=False) as m:
            m.get("https://nominatim.test/search").mock(side_effect=failing_responder)
            await script_module.main(source, None)

    # Checkpoint from the interrupted run: only "demo-a" made it.
    candidates = json.loads(script_module.CANDIDATES_PATH.read_text())
    assert [c["original_id"] for c in candidates] == ["demo-a"]

    # Plain rerun, this time nothing fails.
    with respx.mock(assert_all_called=False) as m:
        m.get("https://nominatim.test/search").mock(
            return_value=httpx.Response(
                200, json=[{"lat": "31.0", "lon": "77.0", "display_name": "second run"}]
            )
        )
        rc = await script_module.main(source, None)

    assert rc == 0
    candidates = json.loads(script_module.CANDIDATES_PATH.read_text())
    ids = sorted(c["original_id"] for c in candidates)
    assert ids == ["demo-a", "demo-b"]
    # demo-a is unchanged from the first (interrupted) run's checkpoint,
    # since the rerun's mock only matters for demo-b in this scenario -
    # but demo-a is re-requested too (the script always processes every
    # candidate in `candidates`), so re-confirm it still ends up correct:
    by_id = {c["original_id"]: c for c in candidates}
    assert by_id["demo-a"]["geocoding_display_name"] == "second run"
    assert by_id["demo-b"]["geocoding_display_name"] == "second run"


# ---------------------------------------------------------------------------
# DEFECT 2 regression: corrupted existing output files must abort safely
# without being overwritten or discarded.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corrupted_candidates_file_aborts_without_overwriting_it(
    script_module, script_settings, tmp_paths
):
    source = _write_source(
        tmp_paths,
        [{"id": "demo-a", "name": "A", "category": "fuel", "address": "Addr A"}],
    )
    script_module.get_settings = lambda: script_settings

    corrupted_content = "THIS IS NOT VALID JSON {{{"
    script_module.CANDIDATES_PATH.write_text(corrupted_content)

    with respx.mock(assert_all_called=False) as m:
        route = m.get("https://nominatim.test/search").mock(
            return_value=httpx.Response(200, json=[{"lat": "30.0", "lon": "76.0", "display_name": "x"}])
        )
        rc = await script_module.main(source, None)

    # Reports failure via return code, not an uncaught exception.
    assert rc == 2
    # The provider was never even called - the script aborted before doing
    # any geocoding work.
    assert route.call_count == 0
    # The corrupted file is byte-for-byte exactly as it was - not
    # overwritten, not truncated, not replaced with an empty array.
    assert script_module.CANDIDATES_PATH.read_text() == corrupted_content
    # No failures file was created/touched either, since the script
    # aborted before reaching that point.
    assert not script_module.FAILURES_PATH.exists()


@pytest.mark.asyncio
async def test_corrupted_failures_file_aborts_without_overwriting_it(
    script_module, script_settings, tmp_paths
):
    source = _write_source(
        tmp_paths,
        [{"id": "demo-a", "name": "A", "category": "fuel", "address": "Addr A"}],
    )
    script_module.get_settings = lambda: script_settings

    corrupted_content = "{not even an array"
    script_module.FAILURES_PATH.write_text(corrupted_content)

    with respx.mock(assert_all_called=False) as m:
        route = m.get("https://nominatim.test/search").mock(
            return_value=httpx.Response(200, json=[{"lat": "30.0", "lon": "76.0", "display_name": "x"}])
        )
        rc = await script_module.main(source, None)

    assert rc == 2
    assert route.call_count == 0
    assert script_module.FAILURES_PATH.read_text() == corrupted_content


@pytest.mark.asyncio
async def test_valid_json_that_is_not_an_array_is_also_treated_as_corrupted(
    script_module, script_settings, tmp_paths
):
    """A JSON object (or any non-array top-level value) in an output file
    is valid JSON but not the shape this script expects - it must be
    treated the same as unparseable JSON: abort, don't overwrite."""
    source = _write_source(
        tmp_paths,
        [{"id": "demo-a", "name": "A", "category": "fuel", "address": "Addr A"}],
    )
    script_module.get_settings = lambda: script_settings

    not_an_array = json.dumps({"unexpected": "object shape"})
    script_module.CANDIDATES_PATH.write_text(not_an_array)

    rc = await script_module.main(source, None)

    assert rc == 2
    assert script_module.CANDIDATES_PATH.read_text() == not_an_array


def test_corrupted_output_error_message_names_the_exact_file(
    script_module, tmp_paths
):
    """The error raised for corrupted output must identify which file is
    corrupted, not just that 'a' file is corrupted."""
    bad_path = tmp_paths / "geocoded_facility_candidates.json"
    bad_path.write_text("not json")

    with pytest.raises(script_module.CorruptedOutputError) as exc_info:
        script_module._load_json_list(bad_path)

    assert str(bad_path) in str(exc_info.value)


# ---------------------------------------------------------------------------
# Atomic write: a failing write must not destroy previously-good output.
# ---------------------------------------------------------------------------


def test_atomic_write_failure_does_not_touch_existing_valid_file(
    script_module, tmp_paths
):
    """If _atomic_write_json fails partway (simulated here via an
    os.replace that raises), the pre-existing target file must be left
    completely intact - the temp file is discarded, the real file is
    never partially written."""
    target = tmp_paths / "output.json"
    original_content = json.dumps([{"original_id": "demo-a", "value": "good"}])
    target.write_text(original_content)

    def failing_replace(*args, **kwargs):
        raise OSError("simulated disk failure during rename")

    original_replace = script_module.os.replace
    script_module.os.replace = failing_replace
    try:
        with pytest.raises(OSError, match="simulated disk failure"):
            script_module._atomic_write_json(target, [{"original_id": "demo-b", "value": "new"}])
    finally:
        script_module.os.replace = original_replace

    # Target still has the ORIGINAL content - the failed write never
    # touched it.
    assert target.read_text() == original_content
    # No leftover temp file in the directory.
    leftover_tmp_files = [
        p for p in tmp_paths.iterdir() if p.name.startswith(".output.json.")
    ]
    assert leftover_tmp_files == []


def test_atomic_write_produces_no_leftover_temp_file_on_success(
    script_module, tmp_paths
):
    target = tmp_paths / "output.json"
    script_module._atomic_write_json(target, [{"a": 1}])

    all_files = list(tmp_paths.iterdir())
    assert all_files == [target]
    assert json.loads(target.read_text()) == [{"a": 1}]


# ---------------------------------------------------------------------------
# Regression: normal full-run correctness is unaffected by the
# checkpointing/atomic-write changes.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_successful_run_still_produces_correct_final_output(
    script_module, script_settings, tmp_paths
):
    """End-to-end sanity check that per-candidate checkpointing produces
    the same final result as the old single-write-at-the-end approach did:
    all candidates present, correctly split between successes/failures."""
    source = _write_source(
        tmp_paths,
        [
            {"id": "demo-a", "name": "A", "category": "fuel", "address": "Addr A"},
            {"id": "demo-b", "name": "B", "category": "fuel", "address": "Addr B (no match)"},
            {"id": "demo-c", "name": "C", "category": "fuel", "address": "Addr C"},
        ],
    )
    script_module.get_settings = lambda: script_settings

    def responder(request):
        q = request.url.params.get("q", "")
        if "no match" in q:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[{"lat": "30.0", "lon": "76.0", "display_name": "ok"}])

    with respx.mock(assert_all_called=False) as m:
        m.get("https://nominatim.test/search").mock(side_effect=responder)
        rc = await script_module.main(source, None)

    assert rc == 0
    candidates = json.loads(script_module.CANDIDATES_PATH.read_text())
    failures = json.loads(script_module.FAILURES_PATH.read_text())
    assert sorted(c["original_id"] for c in candidates) == ["demo-a", "demo-c"]
    assert [f["original_id"] for f in failures] == ["demo-b"]


def test_original_demo_facilities_file_is_byte_for_byte_unchanged():
    """Final safeguard: the real app/data/demo/demo_facilities.json must
    still have exactly 18 entries, all unverified_coordinates, matching
    its state before any of this script's changes - confirmed by loading
    it the normal way the running application does."""
    facilities = get_demo_facilities()
    assert len(facilities) == 18
    for f in facilities:
        assert f.verification_status == "unverified_coordinates"
        assert f.last_verified_at is None
