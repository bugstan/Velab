"""
PDF / 文本文档切块服务

将技术文档切分为可检索的 chunks，支持:
- PDF 文件 (使用 pdfplumber 或 PyPDF2)
- 纯文本 / Markdown 文件
- 按段落 / 固定长度切块
- 重叠窗口切块（提高检索召回率）

作者：FOTA 诊断平台团队
创建时间：2026-04-06
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """文档切块"""
    chunk_id: str
    doc_title: str
    doc_path: str
    content: str
    chunk_index: int
    total_chunks: int
    char_offset: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class DocumentChunker:
    """
    文档切块服务

    支持多种切块策略:
    1. 固定长度切块 (fixed_size)
    2. 段落感知切块 (paragraph)
    3. 滑动窗口切块 (sliding_window)
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        min_chunk_size: int = 50,
    ):
        """
        Args:
            chunk_size: 每个 chunk 的目标字符数
            chunk_overlap: 相邻 chunk 的重叠字符数
            min_chunk_size: 最小 chunk 大小（小于此值合并到前一个）
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def chunk_file(self, file_path: Path) -> List[DocumentChunk]:
        """
        切块单个文件

        自动检测文件类型并选择合适的提取方法。

        Args:
            file_path: 文件路径

        Returns:
            切块列表
        """
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            text = self._extract_pdf_text(file_path)
        elif suffix in (".txt", ".md", ".log"):
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        else:
            logger.warning("Unsupported file type: %s", suffix)
            return []

        if not text.strip():
            return []

        title = file_path.stem
        return self.chunk_text(text, title=title, doc_path=str(file_path))

    def chunk_text(
        self,
        text: str,
        title: str = "untitled",
        doc_path: str = "",
        strategy: str = "paragraph",
    ) -> List[DocumentChunk]:
        """
        切块文本内容

        Args:
            text: 原始文本
            title: 文档标题
            doc_path: 文档路径
            strategy: 切块策略 (paragraph / fixed_size / sliding_window)

        Returns:
            切块列表
        """
        if strategy == "paragraph":
            raw_chunks = self._chunk_by_paragraph(text)
        elif strategy == "sliding_window":
            raw_chunks = self._chunk_sliding_window(text)
        else:
            raw_chunks = self._chunk_fixed_size(text)

        # 过滤掉过小的 chunk
        filtered = []
        for content, offset in raw_chunks:
            content = content.strip()
            if len(content) >= self.min_chunk_size:
                filtered.append((content, offset))
            elif filtered:
                # 合并到前一个 chunk
                prev_content, prev_offset = filtered[-1]
                filtered[-1] = (prev_content + "\n" + content, prev_offset)

        # 生成 DocumentChunk 对象
        total = len(filtered)
        chunks = []
        for idx, (content, offset) in enumerate(filtered):
            chunk = DocumentChunk(
                chunk_id=f"{title}_{idx}",
                doc_title=title,
                doc_path=doc_path,
                content=content,
                chunk_index=idx,
                total_chunks=total,
                char_offset=offset,
                metadata={
                    "strategy": strategy,
                    "char_count": len(content),
                },
            )
            chunks.append(chunk)

        logger.info(
            "Chunked '%s': %d chunks (strategy=%s, avg_size=%d)",
            title,
            total,
            strategy,
            sum(len(c.content) for c in chunks) // max(total, 1),
        )
        return chunks

    def chunk_directory(
        self,
        dir_path: Path,
        extensions: Optional[List[str]] = None,
    ) -> List[DocumentChunk]:
        """
        批量切块目录中的文件

        Args:
            dir_path: 目录路径
            extensions: 要处理的文件扩展名列表

        Returns:
            所有文件的切块列表
        """
        if extensions is None:
            extensions = [".pdf", ".txt", ".md"]

        all_chunks = []
        for f in sorted(dir_path.iterdir()):
            if f.is_file() and f.suffix.lower() in extensions:
                chunks = self.chunk_file(f)
                all_chunks.extend(chunks)

        logger.info("Directory chunking complete: %d total chunks", len(all_chunks))
        return all_chunks

    # ── 切块策略 ──

    def _chunk_by_paragraph(self, text: str) -> List[tuple[str, int]]:
        """按段落切块"""
        paragraphs = re.split(r"\n\s*\n+", text)
        chunks = []
        current_chunk = ""
        current_offset = 0
        running_offset = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                running_offset += 2
                continue

            if len(current_chunk) + len(para) + 1 <= self.chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
                    current_offset = running_offset
            else:
                if current_chunk:
                    chunks.append((current_chunk, current_offset))
                current_chunk = para
                current_offset = running_offset

            running_offset += len(para) + 2

        if current_chunk:
            chunks.append((current_chunk, current_offset))

        return chunks

    def _chunk_fixed_size(self, text: str) -> List[tuple[str, int]]:
        """固定长度切块"""
        chunks = []
        for i in range(0, len(text), self.chunk_size):
            chunk = text[i : i + self.chunk_size]
            chunks.append((chunk, i))
        return chunks

    def _chunk_sliding_window(self, text: str) -> List[tuple[str, int]]:
        """滑动窗口切块（带重叠）"""
        chunks = []
        step = self.chunk_size - self.chunk_overlap
        if step <= 0:
            step = self.chunk_size // 2

        for i in range(0, len(text), step):
            chunk = text[i : i + self.chunk_size]
            if len(chunk) >= self.min_chunk_size:
                chunks.append((chunk, i))
            if i + self.chunk_size >= len(text):
                break

        return chunks

    # ── PDF 提取 ──

    @staticmethod
    def _extract_pdf_text(file_path: Path) -> str:
        """
        提取 PDF 文本

        尝试使用 pdfplumber（优先）或 PyPDF2 提取文本。
        """
        # 尝试 pdfplumber
        try:
            import pdfplumber

            text_parts = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            if text_parts:
                return "\n\n".join(text_parts)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("pdfplumber failed for %s: %s", file_path, e)

        # 尝试 PyPDF2
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(str(file_path))
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            if text_parts:
                return "\n\n".join(text_parts)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("PyPDF2 failed for %s: %s", file_path, e)

        logger.error(
            "Cannot extract text from PDF %s: install pdfplumber or PyPDF2",
            file_path,
        )
        return ""


# 全局单例
doc_chunker = DocumentChunker()
