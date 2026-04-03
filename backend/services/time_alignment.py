"""
Time Alignment Service - 多域日志时间对齐服务

车端多域日志存在异构时钟问题：
- Android: wall clock（绝对时间）
- MCU: uptime（相对时间，从启动开始计数）
- DLT: 可能存在异常时间
- iBDU: 独立时钟

本模块通过识别锚点事件（同一物理事件在多个日志源中的时间戳），
计算时钟偏移量，将所有事件统一到标准化时间轴上。

作者：FOTA 诊断平台团队
创建时间：2026-04-03
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from enum import Enum
import re


class AlignmentStatus(str, Enum):
    """时间对齐状态"""
    SUCCESS = "SUCCESS"  # 全部域对齐成功
    PARTIAL = "PARTIAL"  # 部分域对齐成功
    FAILED = "FAILED"    # 全部域对齐失败


@dataclass
class AnchorEvent:
    """
    锚点事件
    
    用于跨域时间对齐的基准事件，必须在多个日志源中都能识别。
    """
    event_type: str  # 事件类型（如 "system_boot", "network_connected"）
    description: str  # 事件描述
    timestamps: Dict[str, datetime] = field(default_factory=dict)  # {source_type: timestamp}
    confidence: float = 1.0  # 识别置信度


@dataclass
class ClockOffset:
    """
    时钟偏移量
    
    记录某个日志源相对于参考时钟的偏移量和置信度。
    """
    source_type: str  # 日志来源类型
    offset_seconds: float  # 偏移量（秒）
    confidence: float  # 置信度 (0.0-1.0)
    reference_source: str  # 参考时钟来源
    anchor_count: int  # 用于计算的锚点数量


@dataclass
class AlignmentResult:
    """
    时间对齐结果
    
    包含所有日志源的时钟偏移量和对齐状态。
    """
    status: AlignmentStatus
    offsets: Dict[str, ClockOffset]  # {source_type: ClockOffset}
    reference_source: str  # 参考时钟来源（通常是Android）
    anchor_events: List[AnchorEvent]  # 识别到的锚点事件
    warnings: List[str] = field(default_factory=list)  # 警告信息
    
    def get_normalized_timestamp(
        self,
        source_type: str,
        original_ts: datetime
    ) -> Tuple[datetime, float]:
        """
        将原始时间戳转换为标准化时间戳
        
        Args:
            source_type: 日志来源类型
            original_ts: 原始时间戳
        
        Returns:
            tuple: (标准化时间戳, 置信度)
        """
        if source_type not in self.offsets:
            # 未对齐的日志源，返回原始时间戳，置信度为0
            return original_ts, 0.0
        
        offset = self.offsets[source_type]
        normalized_ts = original_ts + timedelta(seconds=offset.offset_seconds)
        return normalized_ts, offset.confidence


class TimeAlignmentService:
    """
    时间对齐服务
    
    核心功能：
    1. 识别锚点事件（跨域时间同步基准）
    2. 计算时钟偏移量
    3. 生成标准化时间戳
    4. 三级降级策略
    """
    
    # 锚点事件识别规则
    ANCHOR_PATTERNS = {
        "system_boot": {
            "keywords": ["boot", "startup", "init", "starting"],
            "sources": ["android", "mcu", "kernel"],
            "confidence": 0.9,
        },
        "network_connected": {
            "keywords": ["network connected", "wifi connected", "connection established"],
            "sources": ["android", "fota"],
            "confidence": 0.85,
        },
        "fota_download_start": {
            "keywords": ["download start", "downloading", "begin download"],
            "sources": ["android", "fota", "mcu"],
            "confidence": 0.95,
        },
        "fota_install_start": {
            "keywords": ["install start", "installation", "begin install", "flashing"],
            "sources": ["android", "fota", "mcu"],
            "confidence": 0.95,
        },
        "system_reboot": {
            "keywords": ["reboot", "restart", "rebooting"],
            "sources": ["android", "mcu", "kernel"],
            "confidence": 0.9,
        },
    }
    
    def __init__(self, reference_source: str = "android"):
        """
        初始化时间对齐服务
        
        Args:
            reference_source: 参考时钟来源（默认使用Android的wall clock）
        """
        self.reference_source = reference_source
    
    def align_events(
        self,
        events_by_source: Dict[str, List[Dict]]
    ) -> AlignmentResult:
        """
        对多个日志源的事件进行时间对齐
        
        Args:
            events_by_source: 按日志源分组的事件列表
                格式: {source_type: [event_dict, ...]}
                event_dict需包含: original_ts, message
        
        Returns:
            AlignmentResult: 对齐结果
        """
        # 1. 识别锚点事件
        anchor_events = self._identify_anchor_events(events_by_source)
        
        if not anchor_events:
            # 无法找到任何锚点事件，对齐失败
            return AlignmentResult(
                status=AlignmentStatus.FAILED,
                offsets={},
                reference_source=self.reference_source,
                anchor_events=[],
                warnings=["未找到任何锚点事件，无法进行时间对齐"]
            )
        
        # 2. 计算时钟偏移量
        offsets = self._calculate_offsets(anchor_events, events_by_source.keys())
        
        # 3. 评估对齐状态
        status, warnings = self._evaluate_alignment_status(offsets, events_by_source.keys())
        
        return AlignmentResult(
            status=status,
            offsets=offsets,
            reference_source=self.reference_source,
            anchor_events=anchor_events,
            warnings=warnings
        )
    
    def _identify_anchor_events(
        self,
        events_by_source: Dict[str, List[Dict]]
    ) -> List[AnchorEvent]:
        """
        识别锚点事件
        
        在多个日志源中查找相同的物理事件，作为时间对齐的基准。
        
        Args:
            events_by_source: 按日志源分组的事件列表
        
        Returns:
            List[AnchorEvent]: 识别到的锚点事件列表
        """
        anchor_events = []
        
        for event_type, pattern in self.ANCHOR_PATTERNS.items():
            keywords = pattern["keywords"]
            required_sources = pattern["sources"]
            base_confidence = pattern["confidence"]
            
            # 在每个日志源中查找匹配的事件
            matches_by_source = {}
            
            for source_type, events in events_by_source.items():
                if source_type not in required_sources:
                    continue
                
                # 查找第一个匹配的事件
                for event in events:
                    message = event.get("message", "").lower()
                    if any(keyword in message for keyword in keywords):
                        matches_by_source[source_type] = event.get("original_ts")
                        break
            
            # 如果至少在2个日志源中找到匹配，则认为是有效的锚点
            if len(matches_by_source) >= 2:
                anchor = AnchorEvent(
                    event_type=event_type,
                    description=f"Anchor event: {event_type}",
                    timestamps=matches_by_source,
                    confidence=base_confidence
                )
                anchor_events.append(anchor)
        
        return anchor_events
    
    def _calculate_offsets(
        self,
        anchor_events: List[AnchorEvent],
        all_sources: set
    ) -> Dict[str, ClockOffset]:
        """
        计算时钟偏移量
        
        基于锚点事件，计算每个日志源相对于参考时钟的偏移量。
        
        Args:
            anchor_events: 锚点事件列表
            all_sources: 所有日志源类型
        
        Returns:
            Dict[str, ClockOffset]: 时钟偏移量字典
        """
        offsets = {}
        
        # 参考时钟的偏移量为0
        offsets[self.reference_source] = ClockOffset(
            source_type=self.reference_source,
            offset_seconds=0.0,
            confidence=1.0,
            reference_source=self.reference_source,
            anchor_count=len(anchor_events)
        )
        
        # 计算其他日志源的偏移量
        for source_type in all_sources:
            if source_type == self.reference_source:
                continue
            
            # 收集该日志源在所有锚点事件中的偏移量
            offset_samples = []
            
            for anchor in anchor_events:
                if source_type in anchor.timestamps and self.reference_source in anchor.timestamps:
                    ref_ts = anchor.timestamps[self.reference_source]
                    src_ts = anchor.timestamps[source_type]
                    
                    # 计算偏移量（秒）
                    offset = (ref_ts - src_ts).total_seconds()
                    offset_samples.append((offset, anchor.confidence))
            
            if offset_samples:
                # 使用加权平均计算最终偏移量
                total_weight = sum(conf for _, conf in offset_samples)
                weighted_offset = sum(offset * conf for offset, conf in offset_samples) / total_weight
                
                # 计算置信度（基于样本数量和一致性）
                confidence = self._calculate_confidence(offset_samples)
                
                offsets[source_type] = ClockOffset(
                    source_type=source_type,
                    offset_seconds=weighted_offset,
                    confidence=confidence,
                    reference_source=self.reference_source,
                    anchor_count=len(offset_samples)
                )
        
        return offsets
    
    def _calculate_confidence(
        self,
        offset_samples: List[Tuple[float, float]]
    ) -> float:
        """
        计算时钟偏移量的置信度
        
        考虑因素：
        1. 样本数量（越多越好）
        2. 样本一致性（方差越小越好）
        3. 锚点事件的基础置信度
        
        Args:
            offset_samples: 偏移量样本列表 [(offset, confidence), ...]
        
        Returns:
            float: 置信度 (0.0-1.0)
        """
        if not offset_samples:
            return 0.0
        
        # 基础置信度：基于样本数量
        sample_count = len(offset_samples)
        sample_confidence = min(sample_count / 2.0, 1.0)  # 2个样本达到满分
        
        # 锚点置信度：使用锚点事件的平均置信度
        anchor_confidences = [conf for _, conf in offset_samples]
        avg_anchor_confidence = sum(anchor_confidences) / len(anchor_confidences)
        
        # 一致性因子：基于方差
        offsets = [offset for offset, _ in offset_samples]
        consistency_factor = 1.0
        
        if len(offsets) > 1:
            mean_offset = sum(offsets) / len(offsets)
            variance = sum((o - mean_offset) ** 2 for o in offsets) / len(offsets)
            std_dev = variance ** 0.5
            
            # 如果标准差超过5秒，降低置信度
            if std_dev > 5:
                consistency_factor = max(0.6, 1.0 - (std_dev - 5) / 50)
        
        # 综合置信度 = 样本数量 × 锚点置信度 × 一致性因子
        final_confidence = sample_confidence * avg_anchor_confidence * consistency_factor
        
        return min(final_confidence, 1.0)
    
    def _evaluate_alignment_status(
        self,
        offsets: Dict[str, ClockOffset],
        all_sources: set
    ) -> Tuple[AlignmentStatus, List[str]]:
        """
        评估时间对齐状态
        
        Args:
            offsets: 时钟偏移量字典
            all_sources: 所有日志源类型
        
        Returns:
            tuple: (对齐状态, 警告信息列表)
        """
        warnings = []
        
        # 统计对齐情况
        aligned_sources = set(offsets.keys())
        unaligned_sources = all_sources - aligned_sources
        
        # 统计高置信度对齐的日志源
        high_confidence_sources = {
            src for src, offset in offsets.items()
            if offset.confidence >= 0.8
        }
        
        # 判断对齐状态
        if len(unaligned_sources) == 0 and len(high_confidence_sources) == len(aligned_sources):
            # 全部域对齐成功，且置信度都很高
            status = AlignmentStatus.SUCCESS
        elif len(high_confidence_sources) >= len(aligned_sources) * 0.5:
            # 至少一半的日志源高置信度对齐
            status = AlignmentStatus.PARTIAL
            
            # 添加警告信息
            for src in unaligned_sources:
                warnings.append(f"日志源 {src} 未找到锚点事件，无法对齐")
            
            for src, offset in offsets.items():
                if offset.confidence < 0.8:
                    warnings.append(
                        f"日志源 {src} 对齐置信度较低 ({offset.confidence:.2f})，"
                        f"时序结论可能不准确"
                    )
        else:
            # 大部分日志源对齐失败
            status = AlignmentStatus.FAILED
            warnings.append(
                "⚠️ 时间对齐失败，本报告时序结论不可信，仅供参考，请人工复核"
            )
        
        return status, warnings
