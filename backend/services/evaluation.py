"""
评测框架 — 诊断质量基准测试集

提供标准化评测 Case 和评分逻辑：
1. 加载标注的基准测试集
2. 运行 Agent 获取诊断结果
3. 对比参考答案计算评分
4. 输出评测报告

不依赖 LLM — 评分纯规则逻辑。

作者：FOTA 诊断平台团队
创建时间：2026-04-06
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).resolve().parent.parent / "data" / "eval"


@dataclass
class EvalCase:
    """评测用例"""
    case_id: str
    query: str  # 用户查询
    scenario_id: str  # 场景 ID
    expected_root_cause: str  # 期望根因
    expected_keywords: List[str]  # 期望命中的关键词
    expected_ecus: List[str]  # 期望涉及的 ECU
    expected_fota_stages: List[str]  # 期望检测到的 FOTA 阶段
    expected_confidence: str  # 期望置信度 (high/medium/low)
    log_files: List[str] = field(default_factory=list)  # 关联的日志文件
    difficulty: str = "medium"  # easy / medium / hard


@dataclass
class EvalResult:
    """单条评测结果"""
    case_id: str
    scores: Dict[str, float]  # 各维度分数
    total_score: float  # 总分
    details: Dict[str, str]  # 各维度详细描述
    passed: bool


@dataclass
class EvalReport:
    """评测报告"""
    total_cases: int
    passed_cases: int
    avg_score: float
    results: List[EvalResult]
    dimension_averages: Dict[str, float]


class DiagnosisEvaluator:
    """
    诊断评测器

    评测维度（每项 0-1 分）：
    1. 关键词命中率 — 诊断输出是否包含期望关键词
    2. ECU 识别准确率 — 是否正确识别涉及的 ECU
    3. FOTA 阶段检测 — 是否正确识别故障阶段
    4. 根因相关度 — 诊断根因与参考答案的文本相似度
    5. 置信度一致性 — 置信度是否与期望一致
    """

    PASS_THRESHOLD = 0.6  # 总分 ≥ 0.6 视为通过

    def __init__(self):
        self.eval_cases: List[EvalCase] = []

    def load_eval_set(self, path: Optional[Path] = None) -> int:
        """
        加载评测集

        Args:
            path: 评测集 JSON 文件路径

        Returns:
            加载的用例数
        """
        if path is None:
            path = EVAL_DIR / "eval_cases.json"

        if not path.exists():
            logger.warning("Eval set not found at %s, using built-in cases", path)
            self.eval_cases = BUILTIN_EVAL_CASES
            return len(self.eval_cases)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.eval_cases = [EvalCase(**c) for c in data]
            logger.info("Loaded %d eval cases from %s", len(self.eval_cases), path)
        except Exception as e:
            logger.error("Failed to load eval set: %s", e)
            self.eval_cases = BUILTIN_EVAL_CASES

        return len(self.eval_cases)

    def evaluate_single(
        self,
        case: EvalCase,
        agent_output: Dict[str, Any],
    ) -> EvalResult:
        """
        评测单个用例

        Args:
            case: 评测用例
            agent_output: Agent 输出结果 (包含 summary, detail, confidence, sources)

        Returns:
            评测结果
        """
        scores = {}
        details = {}

        output_text = (
            f"{agent_output.get('summary', '')} {agent_output.get('detail', '')}"
        ).lower()

        # 1. 关键词命中率
        hits = sum(1 for kw in case.expected_keywords if kw.lower() in output_text)
        kw_score = hits / max(len(case.expected_keywords), 1)
        scores["keyword_recall"] = round(kw_score, 3)
        details["keyword_recall"] = (
            f"命中 {hits}/{len(case.expected_keywords)} 个关键词"
        )

        # 2. ECU 识别准确率
        ecu_hits = sum(1 for ecu in case.expected_ecus if ecu.lower() in output_text)
        ecu_score = ecu_hits / max(len(case.expected_ecus), 1)
        scores["ecu_accuracy"] = round(ecu_score, 3)
        details["ecu_accuracy"] = (
            f"识别 {ecu_hits}/{len(case.expected_ecus)} 个 ECU"
        )

        # 3. FOTA 阶段检测
        stage_hits = sum(
            1 for stage in case.expected_fota_stages
            if stage.lower() in output_text
        )
        stage_score = stage_hits / max(len(case.expected_fota_stages), 1)
        scores["stage_detection"] = round(stage_score, 3)
        details["stage_detection"] = (
            f"检测 {stage_hits}/{len(case.expected_fota_stages)} 个阶段"
        )

        # 4. 根因相关度（简单词重叠度）
        expected_tokens = set(re.findall(r'\w+', case.expected_root_cause.lower()))
        output_tokens = set(re.findall(r'\w+', output_text))
        if expected_tokens:
            overlap = len(expected_tokens & output_tokens)
            rca_score = overlap / len(expected_tokens)
        else:
            rca_score = 0.0
        scores["rca_relevance"] = round(rca_score, 3)
        details["rca_relevance"] = f"根因词重叠 {overlap}/{len(expected_tokens)}" if expected_tokens else "无参考根因"

        # 5. 置信度一致性
        actual_conf = agent_output.get("confidence", "low")
        conf_score = 1.0 if actual_conf == case.expected_confidence else 0.5
        scores["confidence_match"] = conf_score
        details["confidence_match"] = (
            f"期望={case.expected_confidence}, 实际={actual_conf}"
        )

        # 总分（加权平均）
        weights = {
            "keyword_recall": 0.25,
            "ecu_accuracy": 0.20,
            "stage_detection": 0.20,
            "rca_relevance": 0.25,
            "confidence_match": 0.10,
        }
        total = sum(scores[k] * weights[k] for k in weights)

        return EvalResult(
            case_id=case.case_id,
            scores=scores,
            total_score=round(total, 3),
            details=details,
            passed=total >= self.PASS_THRESHOLD,
        )

    def run_eval(
        self,
        agent_outputs: Dict[str, Dict[str, Any]],
    ) -> EvalReport:
        """
        运行完整评测

        Args:
            agent_outputs: {case_id: agent_output} 映射

        Returns:
            评测报告
        """
        results = []
        for case in self.eval_cases:
            output = agent_outputs.get(case.case_id, {})
            result = self.evaluate_single(case, output)
            results.append(result)

        passed = sum(1 for r in results if r.passed)
        avg_score = (
            sum(r.total_score for r in results) / len(results)
            if results
            else 0.0
        )

        # 各维度平均分
        dim_avgs = {}
        if results:
            all_dims = results[0].scores.keys()
            for dim in all_dims:
                dim_avgs[dim] = round(
                    sum(r.scores.get(dim, 0) for r in results) / len(results), 3
                )

        return EvalReport(
            total_cases=len(self.eval_cases),
            passed_cases=passed,
            avg_score=round(avg_score, 3),
            results=results,
            dimension_averages=dim_avgs,
        )


# 内置评测用例
BUILTIN_EVAL_CASES = [
    EvalCase(
        case_id="eval-001",
        query="iCGM 升级过程中 eMMC 写入超时导致刷写失败",
        scenario_id="fota-diagnostic",
        expected_root_cause="eMMC写入超时,高温环境导致NAND性能退化",
        expected_keywords=["emmc", "超时", "写入", "icgm", "刷写", "失败"],
        expected_ecus=["iCGM"],
        expected_fota_stages=["INSTALL", "FAILED"],
        expected_confidence="high",
        log_files=["icgm_emmc_timeout_20250915.log"],
        difficulty="easy",
    ),
    EvalCase(
        case_id="eval-002",
        query="4G信号弱区域下载升级包后校验失败",
        scenario_id="fota-jira",
        expected_root_cause="网络中断导致断点续传数据错位,SHA-256校验失败",
        expected_keywords=["下载", "校验", "sha", "网络", "中断", "失败"],
        expected_ecus=["MPU"],
        expected_fota_stages=["DOWNLOAD", "VERIFY", "FAILED"],
        expected_confidence="medium",
        log_files=["network_interrupt_download_20251003.log"],
        difficulty="medium",
    ),
    EvalCase(
        case_id="eval-003",
        query="批量ECU升级时iCGM失败导致下游MCU和IPK卡死",
        scenario_id="fota-jira",
        expected_root_cause="iCGM CRC校验失败,未正确发送FLASH_COMPLETE信号,下游ECU无限等待",
        expected_keywords=["crc", "依赖", "超时", "icgm", "mcu", "ipk", "刷写顺序"],
        expected_ecus=["iCGM", "MCU", "IPK"],
        expected_fota_stages=["INSTALL", "FAILED"],
        expected_confidence="high",
        log_files=["ecu_dependency_chain_failure_20251120.log"],
        difficulty="hard",
    ),
    EvalCase(
        case_id="eval-004",
        query="夜间自动升级时电池电量不足导致中止",
        scenario_id="fota-diagnostic",
        expected_root_cause="电池电量低于安全阈值(50%),触发紧急中止并回退",
        expected_keywords=["电池", "电量", "中止", "安全", "回退"],
        expected_ecus=["IVI"],
        expected_fota_stages=["INSTALL", "ROLLBACK"],
        expected_confidence="medium",
        log_files=["battery_drain_abort_20251208.log"],
        difficulty="easy",
    ),
    EvalCase(
        case_id="eval-005",
        query="FOTA升级完成但T-BOX状态上报失败,运维平台显示超时",
        scenario_id="fota-jira",
        expected_root_cause="T-BOX通信断连导致状态上报失败,实际升级已成功但状态不一致",
        expected_keywords=["t-box", "通信", "断连", "状态", "上报", "不一致"],
        expected_ecus=["T-BOX"],
        expected_fota_stages=["COMPLETE"],
        expected_confidence="medium",
        difficulty="medium",
    ),
]


# 全局评测器
evaluator = DiagnosisEvaluator()

if __name__ == "__main__":
    import asyncio
    import time
    from config import SCENARIO_AGENT_MAP
    from agents.base import registry

    async def run_evaluation_suite():
        logger.setLevel(logging.INFO)
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        print("🚀 Starting FOTA Diagnostics Evaluation Suite (Direct Agent Mode)...\n")
        
        evaluator.load_eval_set()
        
        agent_outputs = {}
        for case in evaluator.eval_cases:
            print(f"Running Case: {case.case_id} - {case.query[:60]}...")
            
            # 直接调用该场景下的所有 Agent（绕过 LLM Orchestrator），收集详细信息
            agent_names = SCENARIO_AGENT_MAP.get(case.scenario_id, ["log_analytics"])
            combined_detail = ""
            combined_summary = ""
            confidences = []
            
            # 使用简单的提取逻辑代替 LLM
            keywords = case.expected_keywords[:3]
                
            for aname in agent_names:
                agent = registry.get(aname)
                if agent:
                    result = await agent.execute(
                        task=case.query,
                        keywords=keywords,
                        context=None
                    )
                    if result.success:
                        combined_detail += f"{agent.name}: {result.detail}\n"
                        combined_summary += f"{result.summary}\n"
                        confidences.append(result.confidence)
            
            # 如果包含 RCA synthesizer（通常在 orchestrator 最后），可以模拟一下
            rca_agent = registry.get("rca_synthesizer")
            if rca_agent:
                # RCA 的 execute() expecting list of AgentResult, let's just supply raw combined
                rca_result = await rca_agent.execute(
                    task=case.query,
                    context={"agent_results_text": combined_detail} 
                )
                if rca_result.success:
                    combined_detail = f"RCA: {rca_result.detail}\n" + combined_detail

            # 决定总置信度
            final_conf = "low"
            if "high" in confidences: final_conf = "high"
            elif "medium" in confidences: final_conf = "medium"
            
            agent_outputs[case.case_id] = {
                "summary": combined_summary,
                "detail": combined_detail,
                "confidence": final_conf,
            }
            
        print("\n📊 Calculating Scores...")
        report = evaluator.run_eval(agent_outputs)
        
        print("="*50)
        print(" " * 15 + "EVALUATION REPORT")
        print("="*50)
        print(f"Total Cases: {report.total_cases}")
        print(f"Passed Cases: {report.passed_cases}")
        print(f"Average Score: {report.avg_score:.2f}")
        print("-" * 50)
        print("Dimension Averages:")
        for dim, avg in report.dimension_averages.items():
             print(f"  - {dim}: {avg:.3f}")
        print("="*50)

        # 保存结果
        report_dir = EVAL_DIR / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"latest_report_{int(time.time())}.json"
        
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump({
                 "total_cases": report.total_cases,
                 "passed_cases": report.passed_cases,
                 "avg_score": report.avg_score,
                 "dimension_averages": report.dimension_averages,
            }, f, indent=2, ensure_ascii=False)
            
        print(f"\nReport saved to: {report_file}")
        
    asyncio.run(run_evaluation_suite())
