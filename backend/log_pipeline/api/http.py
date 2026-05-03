from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, FastAPI, File, Query, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from log_pipeline.config import Settings
from log_pipeline.ingest.classifier import Classifier
from log_pipeline.ingest.pipeline import IngestPipeline
from log_pipeline.interfaces import ControllerType
from log_pipeline.query.range_query import (
    RangeQuery,
    RangeQueryParams,
    estimate_total_lines,
    _DEFAULT_LIMIT,
    _HARD_LIMIT,
)
from log_pipeline.query.slim_filter import SlimFilter
from log_pipeline.storage.catalog import Catalog
from log_pipeline.storage.eventdb import EventDB
from log_pipeline.storage.filestore import FileStore

logger = logging.getLogger(__name__)

_UPLOAD_CHUNK = 1 << 20  # 1 MiB
_PLAIN_SUFFIXES = frozenset({".log", ".txt", ".dlt"})
_ARCHIVE_SUFFIXES = frozenset({".zip", ".gz", ".tgz", ".rar"})


def build_pipeline(settings: Settings) -> IngestPipeline:
    settings.ensure_dirs()
    catalog = Catalog(settings.catalog_db)
    filestore = FileStore(settings.store_root)
    classifier = Classifier.from_yaml(settings.classifier_yaml)
    return IngestPipeline(settings, catalog, filestore, classifier)


def init_app_state(app: FastAPI, settings: Settings | None = None) -> None:
    """Populate ``app.state`` with the pipeline + query helpers shared by the
    router's handlers. Call once from the host app's lifespan."""
    settings = settings or Settings.from_env()
    app.state.log_pipeline_settings = settings
    app.state.pipeline = build_pipeline(settings)
    app.state.eventdb = EventDB(settings.catalog_db)
    app.state.slim_filter = (
        SlimFilter.from_yaml(settings.slim_rules_yaml)
        if settings.slim_rules_yaml.exists()
        else SlimFilter.empty()
    )
    app.state.range_query = RangeQuery(
        app.state.pipeline._catalog, app.state.slim_filter
    )
    logger.info(
        "log_pipeline ready store=%s catalog=%s", settings.store_root, settings.catalog_db
    )


def _error(code: str, message: str, http_status: int) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"error": {"code": code, "message": message}},
    )


def _parse_time(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        pass
    try:
        s = value.replace("Z", "+00:00")
        return datetime.fromisoformat(s).astimezone(timezone.utc).timestamp()
    except ValueError as e:
        raise ValueError(f"could not parse time {value!r}: {e}") from e


router = APIRouter()


@router.post("/bundles", status_code=200, response_model=None)
async def upload_bundle(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> JSONResponse | dict[str, Any]:
    if not file.filename:
        return _error("MISSING_FILENAME", "file has no filename", 400)

    suffix = Path(file.filename).suffix.lower()
    _is_archive = suffix in _ARCHIVE_SUFFIXES or file.filename.lower().endswith(
        (".tar.gz", ".tar")
    )
    _is_plain = suffix in _PLAIN_SUFFIXES
    if not _is_archive and not _is_plain:
        return _error(
            "UNSUPPORTED_FORMAT",
            f"accepted: .zip / .tar.gz / .tgz / .tar / .rar / .log / .txt / .dlt (got {file.filename!r})",
            400,
        )

    settings: Settings = request.app.state.log_pipeline_settings
    upload_id = uuid.uuid4().hex
    upload_path = settings.upload_root / f"{upload_id}__{Path(file.filename).name}"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    partial = upload_path.with_suffix(upload_path.suffix + ".partial")
    with open(partial, "wb") as out:
        while True:
            chunk = await file.read(_UPLOAD_CHUNK)
            if not chunk:
                break
            out.write(chunk)
    partial.replace(upload_path)

    pipeline: IngestPipeline = request.app.state.pipeline
    bundle_id = pipeline.register_upload(upload_path, file.filename)

    def _run() -> None:
        try:
            pipeline.run(bundle_id, upload_path)
        finally:
            try:
                upload_path.unlink(missing_ok=True)
            except OSError:
                pass

    background_tasks.add_task(_run)
    return {"bundle_id": str(bundle_id), "status": "queued"}


@router.get("/bundles/{bundle_id}", response_model=None)
async def get_bundle(request: Request, bundle_id: str) -> JSONResponse | dict:
    try:
        bid = UUID(bundle_id)
    except ValueError:
        return _error("INVALID_BUNDLE_ID", f"not a uuid: {bundle_id!r}", 400)

    pipeline: IngestPipeline = request.app.state.pipeline
    catalog: Catalog = pipeline._catalog
    bundle = catalog.get_bundle(bid)
    if bundle is None:
        return _error("BUNDLE_NOT_FOUND", f"bundle {bundle_id} not found", 404)

    files = catalog.list_files_by_bundle(bid)
    per_ctrl = catalog.count_by_controller(bid)
    per_ctrl_time_range = catalog.valid_time_range_by_controller(bid)
    return {
        "bundle_id": bundle_id,
        "status": bundle["status"],
        "progress": bundle["progress"],
        "archive_filename": bundle["archive_filename"],
        "archive_size_bytes": bundle["archive_size_bytes"],
        "error": bundle["error"],
        "file_count": len(files),
        "files_by_controller": per_ctrl,
        "valid_time_range_by_controller": per_ctrl_time_range,
    }


@router.get("/bundles/{bundle_id}/logs", response_model=None)
async def get_logs(
    request: Request,
    bundle_id: str,
    start: str = Query(..., description="ISO8601 or unix-seconds; aligned (tbox) clock"),
    end: str = Query(...),
    controllers: Optional[str] = Query(None, description="comma-separated"),
    format: str = Query("full", pattern="^(full|slim)$"),
    include_unsynced: bool = Query(False),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_HARD_LIMIT),
) -> StreamingResponse | JSONResponse:
    try:
        bid = UUID(bundle_id)
    except ValueError:
        return _error("INVALID_BUNDLE_ID", f"not a uuid: {bundle_id!r}", 400)

    try:
        t_start = _parse_time(start)
        t_end = _parse_time(end)
    except ValueError as e:
        return _error("INVALID_TIME", str(e), 400)
    if t_end < t_start:
        return _error("INVALID_TIME_RANGE", "end < start", 400)

    ctrl_list: Optional[list[ControllerType]] = None
    if controllers:
        try:
            ctrl_list = [ControllerType(c.strip()) for c in controllers.split(",") if c.strip()]
        except ValueError as e:
            return _error("INVALID_CONTROLLER", str(e), 400)

    params = RangeQueryParams(
        bundle_id=bid,
        start=t_start,
        end=t_end,
        controllers=ctrl_list,
        format=format,
        include_unsynced=include_unsynced,
        limit=limit,
    )
    rq: RangeQuery = request.app.state.range_query
    catalog: Catalog = request.app.state.pipeline._catalog
    if catalog.get_bundle(bid) is None:
        return _error("BUNDLE_NOT_FOUND", f"bundle {bundle_id} not found", 404)

    estimated = estimate_total_lines(catalog, params)
    truncated_estimate = estimated > limit

    def gen() -> Iterator[bytes]:
        for record in rq.stream(params):
            yield json.dumps(record, ensure_ascii=False).encode("utf-8") + b"\n"

    headers = {
        "X-Total-Files-Scanned": "0",
        "X-Truncated": "true" if truncated_estimate else "false",
        "X-Estimated-Lines": str(estimated),
    }
    return StreamingResponse(gen(), media_type="application/x-ndjson", headers=headers)


@router.get("/bundles/{bundle_id}/events", response_model=None)
async def get_events(
    request: Request,
    bundle_id: str,
    types: Optional[str] = Query(None),
    controllers: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
) -> JSONResponse | list:
    try:
        bid = UUID(bundle_id)
    except ValueError:
        return _error("INVALID_BUNDLE_ID", f"not a uuid: {bundle_id!r}", 400)

    catalog: Catalog = request.app.state.pipeline._catalog
    if catalog.get_bundle(bid) is None:
        return _error("BUNDLE_NOT_FOUND", f"bundle {bundle_id} not found", 404)

    type_list = [t.strip() for t in types.split(",")] if types else None
    ctrl_list: Optional[list[ControllerType]] = None
    if controllers:
        try:
            ctrl_list = [ControllerType(c.strip()) for c in controllers.split(",") if c.strip()]
        except ValueError as e:
            return _error("INVALID_CONTROLLER", str(e), 400)
    try:
        t_start = _parse_time(start) if start else None
        t_end = _parse_time(end) if end else None
    except ValueError as e:
        return _error("INVALID_TIME", str(e), 400)

    eventdb: EventDB = request.app.state.eventdb
    return eventdb.list_events(bid, type_list, ctrl_list, t_start, t_end)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Standalone FastAPI app — used by log_pipeline's own tests. The host
    backend wires ``router`` directly via ``init_app_state`` + ``include_router``."""
    from contextlib import asynccontextmanager

    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_app_state(app, settings)
        yield

    app = FastAPI(title="log_pipeline", version="0.1", lifespan=lifespan)
    app.include_router(router, prefix="/api")
    app.include_router(metrics_router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


metrics_router = APIRouter()


@metrics_router.get("/metrics", response_class=PlainTextResponse)
async def metrics(request: Request) -> str:
    catalog: Catalog = request.app.state.pipeline._catalog
    eventdb: EventDB = request.app.state.eventdb
    lines: list[str] = []

    bundle_counts = catalog.count_bundles_by_status()
    lines.append("# HELP log_pipeline_bundles_total Bundles by status")
    lines.append("# TYPE log_pipeline_bundles_total gauge")
    for status, n in bundle_counts.items():
        lines.append(f'log_pipeline_bundles_total{{status="{status}"}} {n}')

    file_counts = catalog.count_files_by_controller_global()
    lines.append("# HELP log_pipeline_files_total Files by controller")
    lines.append("# TYPE log_pipeline_files_total gauge")
    for ctrl, n in file_counts.items():
        lines.append(f'log_pipeline_files_total{{controller="{ctrl}"}} {n}')

    ev_counts = eventdb.count_events_by_type_global()
    lines.append("# HELP log_pipeline_events_extracted_total Important events extracted")
    lines.append("# TYPE log_pipeline_events_extracted_total counter")
    for t, n in ev_counts.items():
        lines.append(f'log_pipeline_events_extracted_total{{event_type="{t}"}} {n}')

    offsets = catalog.list_latest_offsets()
    lines.append("# HELP log_pipeline_alignment_offset_seconds Per-controller offset (latest bundle)")
    lines.append("# TYPE log_pipeline_alignment_offset_seconds gauge")
    lines.append("# HELP log_pipeline_alignment_confidence Per-controller confidence (latest)")
    lines.append("# TYPE log_pipeline_alignment_confidence gauge")
    for ctrl, off, conf in offsets:
        if off is not None:
            lines.append(f'log_pipeline_alignment_offset_seconds{{controller="{ctrl}"}} {off}')
        lines.append(f'log_pipeline_alignment_confidence{{controller="{ctrl}"}} {conf}')

    return "\n".join(lines) + "\n"
