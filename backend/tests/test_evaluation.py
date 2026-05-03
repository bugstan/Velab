"""Tests for DiagnosisEvaluator — evaluate_single scoring logic and run_eval."""
from __future__ import annotations

import json
import pytest

from services.evaluation import (
    DiagnosisEvaluator,
    EvalCase,
    EvalResult,
    EvalReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _case(
    case_id: str = "tc01",
    query: str = "MPU 升级校验失败",
    expected_root_cause: str = "校验失败 重试 超时",
    expected_keywords: list | None = None,
    expected_ecus: list | None = None,
    expected_fota_stages: list | None = None,
    expected_confidence: str = "high",
) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        query=query,
        scenario_id="s1",
        expected_root_cause=expected_root_cause,
        expected_keywords=expected_keywords or ["校验失败", "重试"],
        expected_ecus=expected_ecus or ["MPU"],
        expected_fota_stages=expected_fota_stages or ["verify"],
        expected_confidence=expected_confidence,
    )


def _output(
    summary: str = "MPU 校验失败，重试三次后回退",
    detail: str = "verify 阶段检测到 MPU 校验失败，触发重试机制",
    confidence: str = "high",
) -> dict:
    return {"summary": summary, "detail": detail, "confidence": confidence}


@pytest.fixture
def evaluator() -> DiagnosisEvaluator:
    ev = DiagnosisEvaluator()
    return ev


# ---------------------------------------------------------------------------
# evaluate_single — keyword recall
# ---------------------------------------------------------------------------

class TestKeywordRecall:
    def test_full_hit_gives_score_one(self, evaluator):
        case = _case(expected_keywords=["校验失败", "重试"])
        output = _output(summary="校验失败，已重试", detail="")
        result = evaluator.evaluate_single(case, output)
        assert result.scores["keyword_recall"] == 1.0

    def test_no_hit_gives_score_zero(self, evaluator):
        case = _case(expected_keywords=["完全不相关词语xyz"])
        output = _output(summary="升级成功", detail="")
        result = evaluator.evaluate_single(case, output)
        assert result.scores["keyword_recall"] == 0.0

    def test_partial_hit_gives_proportional_score(self, evaluator):
        case = _case(expected_keywords=["校验失败", "eMMC", "超时"])
        output = _output(summary="校验失败", detail="")  # only 1/3
        result = evaluator.evaluate_single(case, output)
        assert abs(result.scores["keyword_recall"] - 1 / 3) < 0.01

    def test_empty_keywords_gives_score_one(self, evaluator):
        case = _case(expected_keywords=[])
        result = evaluator.evaluate_single(case, _output())
        assert result.scores["keyword_recall"] == 1.0


# ---------------------------------------------------------------------------
# evaluate_single — ECU accuracy
# ---------------------------------------------------------------------------

class TestEcuAccuracy:
    def test_correct_ecu_in_output(self, evaluator):
        case = _case(expected_ecus=["MPU"])
        output = _output(summary="MPU 升级包校验失败", detail="")
        result = evaluator.evaluate_single(case, output)
        assert result.scores["ecu_accuracy"] == 1.0

    def test_wrong_ecu_gives_zero(self, evaluator):
        case = _case(expected_ecus=["iCGM"])
        output = _output(summary="MPU 故障", detail="")
        result = evaluator.evaluate_single(case, output)
        assert result.scores["ecu_accuracy"] == 0.0


# ---------------------------------------------------------------------------
# evaluate_single — FOTA stage detection
# ---------------------------------------------------------------------------

class TestStageDetection:
    def test_correct_stage_detected(self, evaluator):
        case = _case(expected_fota_stages=["verify"])
        output = _output(summary="verify 阶段失败", detail="")
        result = evaluator.evaluate_single(case, output)
        assert result.scores["stage_detection"] == 1.0

    def test_stage_not_detected_gives_zero(self, evaluator):
        case = _case(expected_fota_stages=["install"])
        output = _output(summary="download 阶段失败", detail="")
        result = evaluator.evaluate_single(case, output)
        assert result.scores["stage_detection"] == 0.0


# ---------------------------------------------------------------------------
# evaluate_single — confidence match
# ---------------------------------------------------------------------------

class TestConfidenceMatch:
    def test_exact_match_gives_one(self, evaluator):
        case = _case(expected_confidence="high")
        result = evaluator.evaluate_single(case, _output(confidence="high"))
        assert result.scores["confidence_match"] == 1.0

    def test_mismatch_gives_half(self, evaluator):
        case = _case(expected_confidence="high")
        result = evaluator.evaluate_single(case, _output(confidence="low"))
        assert result.scores["confidence_match"] == 0.5


# ---------------------------------------------------------------------------
# evaluate_single — total score and pass threshold
# ---------------------------------------------------------------------------

class TestTotalScore:
    def test_perfect_output_scores_near_one(self, evaluator):
        case = _case(
            expected_keywords=["校验失败"],
            expected_ecus=["MPU"],
            expected_fota_stages=["verify"],
            expected_confidence="high",
            expected_root_cause="校验失败",
        )
        output = _output(
            summary="MPU verify 阶段校验失败",
            detail="校验失败",
            confidence="high",
        )
        result = evaluator.evaluate_single(case, output)
        assert result.total_score >= 0.8

    def test_empty_output_scores_low(self, evaluator):
        case = _case()
        result = evaluator.evaluate_single(case, {})
        assert result.total_score < 0.4

    def test_passed_flag_set_above_threshold(self, evaluator):
        case = _case(
            expected_keywords=["校验失败"],
            expected_ecus=["MPU"],
            expected_fota_stages=["verify"],
            expected_confidence="high",
            expected_root_cause="校验失败",
        )
        output = _output(
            summary="MPU verify 阶段校验失败",
            detail="校验失败",
            confidence="high",
        )
        result = evaluator.evaluate_single(case, output)
        assert result.passed is True

    def test_passed_flag_false_below_threshold(self, evaluator):
        case = _case()
        result = evaluator.evaluate_single(case, {})
        assert result.passed is False


# ---------------------------------------------------------------------------
# load_eval_set
# ---------------------------------------------------------------------------

class TestLoadEvalSet:
    def test_loads_builtin_when_file_missing(self, evaluator, tmp_path):
        count = evaluator.load_eval_set(tmp_path / "nonexistent.json")
        assert count > 0
        assert evaluator.eval_cases

    def test_loads_custom_json(self, evaluator, tmp_path):
        custom = [
            {
                "case_id": "c1",
                "query": "q",
                "scenario_id": "s1",
                "expected_root_cause": "r",
                "expected_keywords": ["k"],
                "expected_ecus": ["MPU"],
                "expected_fota_stages": ["verify"],
                "expected_confidence": "high",
            }
        ]
        p = tmp_path / "eval.json"
        p.write_text(json.dumps(custom))
        count = evaluator.load_eval_set(p)
        assert count == 1
        assert evaluator.eval_cases[0].case_id == "c1"


# ---------------------------------------------------------------------------
# run_eval — aggregate report
# ---------------------------------------------------------------------------

class TestRunEval:
    def test_report_fields_populated(self, evaluator):
        evaluator.eval_cases = [_case(case_id="tc1"), _case(case_id="tc2")]
        outputs = {
            "tc1": _output(summary="MPU verify 校验失败", detail="校验失败", confidence="high"),
            "tc2": {},
        }
        report = evaluator.run_eval(outputs)
        assert isinstance(report, EvalReport)
        assert report.total_cases == 2
        assert report.passed_cases + (2 - report.passed_cases) == 2
        assert 0.0 <= report.avg_score <= 1.0
        assert len(report.results) == 2

    def test_missing_case_output_treated_as_empty(self, evaluator):
        evaluator.eval_cases = [_case(case_id="tc1")]
        report = evaluator.run_eval({})  # no output provided
        assert report.total_cases == 1
        assert report.avg_score < 0.4

    def test_dimension_averages_keys_present(self, evaluator):
        evaluator.eval_cases = [_case()]
        report = evaluator.run_eval({"tc01": _output()})
        for dim in ("keyword_recall", "ecu_accuracy", "stage_detection",
                    "rca_relevance", "confidence_match"):
            assert dim in report.dimension_averages
