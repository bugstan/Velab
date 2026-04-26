"""
日志压缩包一体化接入服务。

功能：
1. 接收上传文件（zip/tar/txt/log/dlt）
2. 自动解压
3. 按日志类型分类
4. 解析为结构化事件并写入 diagnosis_events
5. 执行时间对齐并回写 normalized_ts / clock_confidence
"""

from __future__ import annotations

import io
import json
import os
import re
import struct
import tarfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, Generator, Iterable, Optional

import redis as redis_sync
from sqlalchemy.orm import Session

from config import settings
from models import Case, DiagnosisEvent, RawLogFile
from models.log_file import ParseStatus
from services.time_alignment import TimeAlignmentService


@dataclass
class IngestResult:
    case_id: str
    uploaded_file: str
    extracted_files: int
    parsed_files: int
    failed_files: int
    total_events: int
    aligned_sources: int
    alignment_status: str


def _sync_task_progress(redis: Optional[redis_sync.Redis], task_id: Optional[str], percent: int, stage: str, message: str) -> None:
    if not task_id or not redis:
        return
    payload = json.dumps(
        {"percent": percent, "stage": stage, "message": message},
        ensure_ascii=False,
    )
    redis.set(f"task_progress:{task_id}", payload, ex=3600)


def _sync_redis_for_progress() -> redis_sync.Redis:
    kwargs: dict = {
        "host": settings.REDIS_HOST,
        "port": settings.REDIS_PORT,
        "decode_responses": True,
    }
    if settings.REDIS_PASSWORD:
        kwargs["password"] = settings.REDIS_PASSWORD
    return redis_sync.Redis(**kwargs)


_ANDROID_RE = re.compile(
    r"^(\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}\.\d+)\s+(\d+)\s+(\d+)\s+([VDIWEF])\s+([^:]+):\s*(.*)"
)
_ANDROID_FILE_YEAR_RE = re.compile(r"saicmaxus@(\d{4})-\d{2}-\d{2}_")

_FOTA_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d+)\s+(DEBUG|INFO|WARN|ERROR|FATAL)\s+\([^)]+\)-\s*\[([^\]]+)\]-(.*)"
)
_FOTA_LEVEL = {"DEBUG": "D", "INFO": "I", "WARN": "W", "ERROR": "E", "FATAL": "F"}

_KERNEL_LINE_RE = re.compile(r"^\[\s*(\d+\.\d+)\]\s*(.*)")
_KERNEL_FILE_RE = re.compile(r"^(\d+)_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.log$")

_MCU_LINE_RE = re.compile(r"^&(\d+)\s+(\w{3})@(\w+):(.*)")
_MCU_RTC_RE = re.compile(r"Rtc Set HW Second:(\d{9,11})")
_MCU_DATE_RE = re.compile(r"Sys Date:\s*(\d{4})\s+(\d{1,2})\s+(\d{1,2})_(\d{1,2}):(\d{1,2}):(\d{1,2})")
_MCU_LEVEL_MAP = {"INF": "I", "WRN": "W", "WAR": "W", "ERR": "E", "DBG": "D", "FAT": "F"}

_IBDU_RE = re.compile(r"^\[(\d{4})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\.(\d+)\](.*)")

_DLT_MAGIC = b"DLT\x01"
_DLT_SH_FMT = struct.Struct("<II4s")


def _event_type_from_level(level: str) -> str:
    if level in ("E", "F"):
        return "ERROR"
    if level == "W":
        return "WARNING"
    return "LOG"


def _ensure_case(db: Session, case_id: str) -> None:
    case = db.query(Case).filter_by(case_id=case_id).first()
    if case:
        return
    db.add(
        Case(
            case_id=case_id,
            vin=None,
            vehicle_model="Unknown",
            issue_description="Auto created by drag-upload ingestion",
            status="active",
            meta_data={"auto_created": True},
        )
    )
    db.commit()


def _safe_extract_zip(src: Path, dst: Path) -> None:
    with zipfile.ZipFile(src, "r") as zf:
        for member in zf.infolist():
            target = (dst / member.filename).resolve()
            if not str(target).startswith(str(dst.resolve())):
                continue
            zf.extract(member, dst)


def _safe_extract_tar(src: Path, dst: Path) -> None:
    with tarfile.open(src, "r:*") as tf:
        for member in tf.getmembers():
            target = (dst / member.name).resolve()
            if not str(target).startswith(str(dst.resolve())):
                continue
            tf.extract(member, dst)


def _classify_file(path: Path) -> Optional[str]:
    name = path.name
    if name.startswith("saicmaxus") and name.endswith(".log"):
        return "android"
    if name.startswith("fotaHMI_") and name.endswith(".log"):
        return "fotahmi"
    if name.startswith("fota_") and name.endswith(".log"):
        return "fota"
    if _KERNEL_FILE_RE.match(name):
        return "kernel"
    if name.endswith(".dlt"):
        return "tbox"
    if name.startswith("MCU_") and name.endswith(".txt"):
        return "mcu"
    if name.startswith("iBDU_") and name.endswith(".txt"):
        return "ibdu"
    return None


def _parse_android(path: Path) -> Generator[dict, None, None]:
    fallback_year = datetime.utcnow().year
    m_year = _ANDROID_FILE_YEAR_RE.search(path.name)
    year = int(m_year.group(1)) if m_year else fallback_year
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for idx, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            m = _ANDROID_RE.match(line)
            if not m:
                continue
            md, hms_us, pid, tid, level, tag, msg = m.groups()
            hms, frac = (hms_us.split(".") + ["0"])[:2]
            frac_us = int(frac.ljust(6, "0")[:6])
            try:
                dt = datetime.strptime(f"{year}-{md} {hms}", "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            ts = dt.replace(tzinfo=timezone.utc).timestamp() + frac_us / 1e6
            yield {
                "timestamp": ts,
                "source_type": "android",
                "level": level,
                "module": tag.strip(),
                "message": msg,
                "raw_line_number": idx,
                "raw_snippet": line,
            }


def _parse_fota(path: Path, source: str) -> Generator[dict, None, None]:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for idx, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            m = _FOTA_RE.match(line)
            if not m:
                continue
            dt_str, ms_str, level, tag, msg = m.groups()
            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            ts = dt.replace(tzinfo=timezone.utc).timestamp() + int(ms_str) / 1000.0
            yield {
                "timestamp": ts,
                "source_type": source,
                "level": _FOTA_LEVEL.get(level, "I"),
                "module": tag,
                "message": msg,
                "raw_line_number": idx,
                "raw_snippet": line,
            }


def _parse_kernel(path: Path) -> Generator[dict, None, None]:
    m = _KERNEL_FILE_RE.match(path.name)
    if not m:
        return
    boot_session = int(m.group(1))
    try:
        boot_dt = datetime.strptime(f"{m.group(2)} {m.group(3).replace('-', ':')}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return
    boot_ts = boot_dt.replace(tzinfo=timezone.utc).timestamp()
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for idx, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            mm = _KERNEL_LINE_RE.match(line)
            if not mm:
                continue
            offset, msg = mm.groups()
            ts = boot_ts + float(offset)
            yield {
                "timestamp": ts,
                "source_type": "kernel",
                "level": "K",
                "module": "kernel",
                "message": msg,
                "raw_line_number": idx,
                "raw_snippet": line,
                "parsed_fields": {"boot_session": boot_session},
            }


def _parse_mcu(path: Path) -> Generator[dict, None, None]:
    parsed = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for idx, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            m = _MCU_LINE_RE.match(line)
            if m:
                parsed.append((idx, int(m.group(1)), m.group(2), m.group(3), m.group(4), line))
    if not parsed:
        return

    sessions = []
    start = 0
    for i in range(1, len(parsed)):
        if parsed[i][1] < parsed[i - 1][1] - 5000:
            sessions.append(parsed[start:i])
            start = i
    sessions.append(parsed[start:])

    for sess_idx, session in enumerate(sessions):
        anchors = []
        for _, counter_ms, _, _, message, _ in session:
            m = _MCU_RTC_RE.search(message)
            if m:
                unix_ts = float(m.group(1))
                if unix_ts > 1_000_000_000:
                    anchors.append((counter_ms, unix_ts))
        if not anchors:
            for _, counter_ms, _, _, message, _ in session:
                m = _MCU_DATE_RE.search(message)
                if not m:
                    continue
                try:
                    dt = datetime(
                        int(m.group(1)),
                        int(m.group(2)),
                        int(m.group(3)),
                        int(m.group(4)),
                        int(m.group(5)),
                        int(m.group(6)),
                    )
                except ValueError:
                    continue
                anchors.append((counter_ms, dt.replace(tzinfo=timezone.utc).timestamp()))
                break
        if not anchors:
            continue

        for line_no, counter_ms, level, module, message, raw_line in session:
            ref_ms, ref_ts = anchors[0]
            for a_ms, a_ts in anchors:
                if a_ms <= counter_ms:
                    ref_ms, ref_ts = a_ms, a_ts
                else:
                    break
            abs_ts = ref_ts + (counter_ms - ref_ms) / 1000.0
            yield {
                "timestamp": abs_ts,
                "source_type": "mcu",
                "level": _MCU_LEVEL_MAP.get(level, "I"),
                "module": module,
                "message": message,
                "raw_line_number": line_no,
                "raw_snippet": raw_line,
                "parsed_fields": {"boot_session": sess_idx},
            }


def _parse_ibdu(path: Path) -> Generator[dict, None, None]:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for idx, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            m = _IBDU_RE.match(line)
            if not m:
                continue
            y, mo, d, h, mi, s, ms_str, msg = m.groups()
            try:
                dt = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
            except ValueError:
                continue
            ms = int(ms_str.ljust(3, "0")[:3])
            ts = dt.replace(tzinfo=timezone.utc).timestamp() + ms / 1000.0
            yield {
                "timestamp": ts,
                "source_type": "ibdu",
                "level": "I",
                "module": "ibdu",
                "message": msg,
                "raw_line_number": idx,
                "raw_snippet": line,
            }


def _extract_text(data: bytes) -> str:
    out = []
    for b in data:
        if 0x20 <= b <= 0x7E or b == 0x09:
            out.append(chr(b))
        elif out and out[-1] != " ":
            out.append(" ")
    return "".join(out).strip()


def _parse_dlt(path: Path) -> Generator[dict, None, None]:
    data = path.read_bytes()
    pos = 0
    total = len(data)
    while pos < total:
        idx = data.find(_DLT_MAGIC, pos)
        if idx == -1 or idx + 20 > total:
            break
        sec, usec, ecu_b = _DLT_SH_FMT.unpack_from(data, idx + 4)
        ts = sec + usec / 1_000_000.0
        htyp = data[idx + 16]
        msg_len = struct.unpack_from(">H", data, idx + 18)[0]
        if msg_len < 4 or idx + 16 + msg_len > total:
            pos = idx + 4
            continue
        msg_end = idx + 16 + msg_len
        payload_start = idx + 20
        if htyp & 0x04:
            payload_start += 4
        if htyp & 0x08:
            payload_start += 4
        if htyp & 0x10:
            payload_start += 4

        app_id = ctx_id = ""
        if (htyp & 0x01) and payload_start + 10 <= msg_end:
            app_id = data[payload_start + 2 : payload_start + 6].decode("ascii", errors="replace").rstrip("\x00 ")
            ctx_id = data[payload_start + 6 : payload_start + 10].decode("ascii", errors="replace").rstrip("\x00 ")
            payload_start += 10

        if payload_start >= msg_end:
            pos = msg_end
            continue
        msg = _extract_text(data[payload_start:msg_end])[:500]
        if not msg:
            pos = msg_end
            continue
        ecu = ecu_b.decode("ascii", errors="replace").rstrip("\x00 ")
        yield {
            "timestamp": ts,
            "source_type": "tbox",
            "level": "I",
            "module": f"{app_id}/{ctx_id}" if app_id else ecu,
            "message": msg,
            "raw_line_number": 0,
            "raw_snippet": msg[:200],
        }
        pos = msg_end


def _parser_for(source: str):
    if source == "android":
        return _parse_android
    if source == "fota":
        return lambda p: _parse_fota(p, "fota")
    if source == "fotahmi":
        return lambda p: _parse_fota(p, "fotahmi")
    if source == "kernel":
        return _parse_kernel
    if source == "mcu":
        return _parse_mcu
    if source == "ibdu":
        return _parse_ibdu
    if source == "tbox":
        return _parse_dlt
    return None


def _to_diagnosis_event(case_id: str, file_id: str, evt: dict) -> DiagnosisEvent:
    ts = datetime.utcfromtimestamp(evt["timestamp"])
    level = evt.get("level", "I")
    return DiagnosisEvent(
        case_id=case_id,
        file_id=file_id,
        source_type=evt["source_type"],
        original_ts=ts,
        normalized_ts=ts,
        clock_confidence=1.0,
        event_type=_event_type_from_level(level),
        module=evt.get("module"),
        level=level,
        message=evt.get("message", ""),
        raw_line_number=evt.get("raw_line_number"),
        raw_snippet=evt.get("raw_snippet"),
        parsed_fields=evt.get("parsed_fields", {}),
        parser_name="drag_upload_ingest",
        parser_version="1.0.0",
    )


def ingest_bundle(
    db: Session,
    case_id: str,
    upload_name: str,
    content: bytes,
    task_id: Optional[str] = None,
) -> IngestResult:
    _ensure_case(db, case_id)

    r: Optional[redis_sync.Redis] = _sync_redis_for_progress() if task_id else None
    _sync_task_progress(r, task_id, 25, "extracting", "正在保存到案例存储…")

    try:
        storage_root = Path(settings.STORAGE_ROOT) / "logs" / case_id
        storage_root.mkdir(parents=True, exist_ok=True)

        ts_label = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        upload_file = storage_root / f"{ts_label}_{upload_name}"
        upload_file.write_bytes(content)

        _sync_task_progress(r, task_id, 28, "extracting", "正在解压并扫描文件（大文件可能需几分钟）…")

        extracted_files = 0
        parsed_files = 0
        failed_files = 0
        total_events = 0
        # 仅对本次入包产生的 file 做时间对齐。case_id 在前端多固定为某场景 id，
        # 若按全 case 查库会把历史上传也拉进来，数据量会指数级拖垮对齐与回写。
        ingested_file_ids: list[str] = []

        with TemporaryDirectory() as td:
            workdir = Path(td)
            extract_dir = workdir / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)

            lname = upload_name.lower()
            if lname.endswith(".zip"):
                _safe_extract_zip(upload_file, extract_dir)
            elif lname.endswith(".tar") or lname.endswith(".tar.gz") or lname.endswith(".tgz"):
                _safe_extract_tar(upload_file, extract_dir)
            else:
                # 非压缩包按单文件处理
                single = extract_dir / upload_name
                single.write_bytes(content)

            _sync_task_progress(r, task_id, 35, "classifying", "解压完成，正在识别待解析的日志…")

            candidates: list[tuple[Path, str, str]] = []
            for root, _, files in os.walk(extract_dir):
                for fname in sorted(files):
                    fpath = Path(root) / fname
                    src = _classify_file(fpath)
                    if src:
                        candidates.append((fpath, fname, src))

            n_cand = len(candidates)
            if n_cand:
                _sync_task_progress(
                    r, task_id, 38, "parsing", f"已识别 {n_cand} 个可解析文件，开始解析与入库…"
                )

            for idx, (fpath, fname, source) in enumerate(candidates, start=1):
                extracted_files += 1
                file_id = f"{case_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{extracted_files:04d}"
                ingested_file_ids.append(file_id)
                raw = RawLogFile(
                    case_id=case_id,
                    file_id=file_id,
                    original_filename=fname,
                    file_size=fpath.stat().st_size,
                    source_type=source,
                    storage_path=str(fpath),
                    parse_status=ParseStatus.PARSING.value,
                    meta_data={"auto_extracted": True, "upload_name": upload_name},
                )
                db.add(raw)
                db.flush()

                parser = _parser_for(source)
                if parser is None:
                    raw.parse_status = ParseStatus.FAILED.value
                    raw.parse_error = f"Unsupported source: {source}"
                    failed_files += 1
                else:
                    try:
                        events = [_to_diagnosis_event(case_id, file_id, evt) for evt in parser(fpath)]
                        if events:
                            db.bulk_save_objects(events)
                            total_events += len(events)
                        raw.parse_status = ParseStatus.PARSED.value
                        parsed_files += 1
                    except Exception as exc:  # noqa: BLE001
                        raw.parse_status = ParseStatus.FAILED.value
                        raw.parse_error = str(exc)[:500]
                        failed_files += 1

                step = max(1, n_cand // 20)
                if n_cand and (idx == 1 or idx == n_cand or idx % step == 0):
                    p = 38 + int(45 * min(idx, n_cand) / n_cand)
                    short = fname if len(fname) <= 48 else f"{fname[:45]}…"
                    _sync_task_progress(
                        r, task_id, min(p, 83), "parsing", f"正在解析 ({idx}/{n_cand}): {short}"
                    )

            if not n_cand:
                _sync_task_progress(r, task_id, 70, "parsing", "未发现可自动分类的日志文件，将跳过逐文件解析")

            db.commit()

        _sync_task_progress(r, task_id, 86, "aligning", "正在对本次入包内事件做时间对齐…")
        alignment = TimeAlignmentService()
        if ingested_file_ids:
            events = (
                db.query(DiagnosisEvent)
                .filter(
                    DiagnosisEvent.case_id == case_id,
                    DiagnosisEvent.file_id.in_(ingested_file_ids),
                )
                .all()
            )
        else:
            events = []
        events_by_source: Dict[str, list] = {}
        for evt in events:
            events_by_source.setdefault(evt.source_type, []).append(
                {"original_ts": evt.original_ts, "message": evt.message}
            )
        aligned_sources = 0
        alignment_status = "FAILED"
        if events_by_source:
            result = alignment.align_events(events_by_source)
            aligned_sources = len(result.offsets)
            alignment_status = result.status.value
            for evt in events:
                normalized, confidence = result.get_normalized_timestamp(evt.source_type, evt.original_ts)
                evt.normalized_ts = normalized
                evt.clock_confidence = confidence
            db.commit()

        _sync_task_progress(r, task_id, 98, "finalizing", "处理完成，汇总结果中…")
        return IngestResult(
            case_id=case_id,
            uploaded_file=upload_name,
            extracted_files=extracted_files,
            parsed_files=parsed_files,
            failed_files=failed_files,
            total_events=total_events,
            aligned_sources=aligned_sources,
            alignment_status=alignment_status,
        )
    finally:
        if r is not None:
            r.close()
