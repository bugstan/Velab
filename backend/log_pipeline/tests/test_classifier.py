from __future__ import annotations

from pathlib import Path

import pytest

from log_pipeline.ingest.classifier import Classifier, _glob_to_regex
from log_pipeline.interfaces import ControllerType


def test_glob_to_regex_handles_double_star_cross_segment():
    p = _glob_to_regex("**/网关&Tbox日志/**")
    assert p.match("raw_logs/日志/网关&Tbox日志/SOIMT-T-UPDATE/foo.dlt")
    assert p.match("a/b/c/网关&Tbox日志/x/y.dlt")
    assert not p.match("foo/网关_unrelated/x.log")


def test_glob_to_regex_single_star_no_cross_segment():
    p = _glob_to_regex("*.dlt")
    assert p.match("foo.dlt")
    assert not p.match("a/b/foo.dlt")


def test_classifier_path_priority(classifier_yaml: Path):
    c = Classifier.from_yaml(classifier_yaml)
    # path-based classification works on real bundle layout
    assert c.classify("raw_logs/日志/娱乐系统日志/android/saicmaxus.log") == ControllerType.ANDROID
    assert (
        c.classify("raw_logs/日志/娱乐系统日志/fota/fotahmilog/fotaHMI_2025-08-07.0.log")
        == ControllerType.FOTA
    )
    assert (
        c.classify("raw_logs/日志/娱乐系统日志/kernel/kernel.log") == ControllerType.KERNEL
    )
    assert (
        c.classify("raw_logs/日志/娱乐系统日志/kernel_logs/176_2025-09-10_14-44-01.log")
        == ControllerType.KERNEL
    )
    assert (
        c.classify("raw_logs/日志/网关&Tbox日志/SOIMT-T-UPDATE/dlt_offlinetrace.0001.dlt")
        == ControllerType.TBOX
    )


def test_classifier_unknown_fallback(classifier_yaml: Path):
    c = Classifier.from_yaml(classifier_yaml)
    assert c.classify("totally/random/path/foo.bin") == ControllerType.UNKNOWN


def test_classifier_name_pattern_when_no_path(classifier_yaml: Path):
    c = Classifier.from_yaml(classifier_yaml)
    # filename match wins when path doesn't help
    assert c.classify("rootless/dlt_offlinetrace.0001.dlt") == ControllerType.TBOX
    assert c.classify("flash_id.txt") == ControllerType.FOTA


def test_classifier_content_sniff_dlt_magic(tmp_path: Path, classifier_yaml: Path):
    p = tmp_path / "weirdname.bin"
    p.write_bytes(b"DLT\x01" + b"\x00" * 200)
    c = Classifier.from_yaml(classifier_yaml)
    # path/name don't match any rule → falls through to content sniffing
    assert c.classify("ambiguous/weirdname.bin", p) == ControllerType.TBOX


def test_classifier_content_sniff_logcat(tmp_path: Path, classifier_yaml: Path):
    p = tmp_path / "ambig.txt"
    p.write_text("09-12 11:24:22.028403   986   986 W TagName: hello\n", encoding="utf-8")
    c = Classifier.from_yaml(classifier_yaml)
    assert c.classify("misc/ambig.txt", p) == ControllerType.ANDROID
