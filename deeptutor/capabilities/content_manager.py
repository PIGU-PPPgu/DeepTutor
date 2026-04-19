"""Content manager capability — multi-format import & knowledge-base indexing."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.llm import complete
from deeptutor.services.llm.config import get_llm_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".epub": "epub",
    ".mobi": "mobi",
    ".txt": "text",
    ".md": "markdown",
    ".markdown": "markdown",
}

CHUNK_SIZE = 4000  # characters per chunk


def _identify_format(source: str, attachments: list) -> dict[str, Any]:
    """Detect content format from source string or attachments."""
    # Check URL patterns
    if source.startswith(("http://", "https://")):
        return {"format": "url", "source": source, "summary": f"Web URL: {source}"}

    # Check attachments
    for att in attachments:
        fn = att.filename.lower()
        if fn.endswith(".pdf"):
            return {"format": "pdf", "source": att.filename, "summary": f"PDF attachment: {att.filename}"}
        if fn.endswith((".epub", ".mobi")):
            return {"format": "epub", "source": att.filename, "summary": f"E-book: {att.filename}"}

    # Check file path
    ext = Path(source).suffix.lower()
    if ext in SUPPORTED_EXTENSIONS:
        fmt = SUPPORTED_EXTENSIONS[ext]
        return {"format": fmt, "source": source, "summary": f"{fmt.upper()} file: {source}"}

    # Fallback: treat as plain text
    return {"format": "text", "source": source, "summary": f"Plain text content ({len(source)} chars)"}


def _chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    """Split text into chunks of roughly *size* characters, breaking at paragraphs."""
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    i = 0
    while i < len(text):
        end = min(i + size, len(text))
        # Try to break at last newline within window
        if end < len(text):
            last_nl = text.rfind("\n", i, end)
            if last_nl > i:
                end = last_nl + 1
        chunks.append(text[i:end])
        i = end
    return chunks


# ---------------------------------------------------------------------------
# Capability
# ---------------------------------------------------------------------------


class ContentManagerCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="content_manager",
        description="Import content in multiple formats and index into knowledge bases.",
        stages=["identify", "process", "index", "verify"],
        tools_used=[],
        cli_aliases=["content", "import"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        source = context.user_message
        attachments = context.attachments
        kb_name = context.metadata.get("knowledge_base", "default")
        config = get_llm_config()

        # --- Stage 1: identify ---
        async with stream.stage("identify", source=self.manifest.name):
            info = _identify_format(source, attachments)
            await stream.thinking(
                f"📂 识别内容：格式={info['format']}，来源={info['source']}",
                source=self.manifest.name,
            )

        # --- Stage 2: process ---
        processed: dict[str, Any] = {}
        async with stream.stage("process", source=self.manifest.name):
            processed = await self._process(info, attachments, config)
            await stream.thinking(
                f"✅ 处理完成：{processed.get('title', '未知标题')} "
                f"({processed.get('word_count', '?')} 字)",
                source=self.manifest.name,
            )

        # --- Stage 3: index ---
        async with stream.stage("index", source=self.manifest.name):
            index_result = await self._index(processed, kb_name)
            await stream.thinking(
                f"🗄️ 入库完成：知识库={kb_name}，分片={index_result['chunks']}",
                source=self.manifest.name,
            )

        # --- Stage 4: verify ---
        async with stream.stage("verify", source=self.manifest.name):
            verify_result = self._verify(index_result)
            status = "✅ 验证通过" if verify_result["ok"] else "⚠️ 验证异常"
            await stream.content(
                f"## 内容导入完成\n\n"
                f"- 标题：{processed.get('title', '未知')}\n"
                f"- 字数：{processed.get('word_count', '?')}\n"
                f"- 知识库：{kb_name}\n"
                f"- 分片数：{index_result['chunks']}\n"
                f"- 状态：{status}",
                source=self.manifest.name,
            )

    # ----- process helpers -----

    async def _process(
        self, info: dict, attachments: list, config: Any
    ) -> dict[str, Any]:
        fmt = info["format"]
        source = info["source"]
        text = ""
        title = ""
        author = ""

        if fmt == "text" or fmt == "markdown":
            # Check if it's a file path that exists
            if os.path.isfile(source):
                text = Path(source).read_text(encoding="utf-8")
                title = Path(source).stem
            else:
                text = source
                title = source[:40]
        elif fmt == "pdf":
            text, title, author = self._extract_pdf(source)
        elif fmt == "epub":
            text, title, author = self._extract_epub(source)
        elif fmt == "url":
            text, title = await self._extract_url(source)
        else:
            text = source
            title = "Unknown"

        # Use LLM to generate metadata
        meta_prompt = (
            f"分析以下文本片段，返回 JSON：{{\"title\": \"标题\", \"author\": \"作者(未知则null)\", \"summary\": \"一句话摘要\"}}\n\n"
            f"文本：{text[:2000]}"
        )
        try:
            raw = await complete(
                prompt=meta_prompt,
                system_prompt="你是内容分析助手，只返回 JSON。",
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=0.3,
            )
            meta = json.loads(raw.strip().strip("`"))
            if not title or title == "Unknown":
                title = meta.get("title", title)
            author = meta.get("author", "")
        except Exception:
            pass

        word_count = len(text)
        return {
            "text": text,
            "title": title,
            "author": author,
            "format": fmt,
            "word_count": word_count,
            "source": source,
        }

    # ----- index helpers -----

    async def _index(self, processed: dict, kb_name: str) -> dict[str, Any]:
        text = processed["text"]
        title = processed["title"]

        # Write to knowledge base directory
        kb_dir = Path(f"data/knowledge_bases/{kb_name}/raw")
        kb_dir.mkdir(parents=True, exist_ok=True)

        chunks = _chunk_text(text)
        files_written: list[str] = []

        if len(chunks) == 1:
            out_path = kb_dir / f"{title}.txt"
            out_path.write_text(text, encoding="utf-8")
            files_written.append(str(out_path))
        else:
            for i, chunk in enumerate(chunks):
                out_path = kb_dir / f"{title}_part{i + 1}.txt"
                out_path.write_text(chunk, encoding="utf-8")
                files_written.append(str(out_path))

        return {
            "kb_name": kb_name,
            "title": title,
            "chunks": len(chunks),
            "files": files_written,
        }

    # ----- verify helpers -----

    def _verify(self, index_result: dict) -> dict[str, Any]:
        all_exist = all(os.path.isfile(f) for f in index_result["files"])
        if all_exist:
            total_size = sum(os.path.getsize(f) for f in index_result["files"])
            return {
                "ok": True,
                "message": (
                    f"共 {index_result['chunks']} 个文件已写入知识库 "
                    f"'{index_result['kb_name']}'，总大小 {total_size} bytes"
                ),
            }
        return {
            "ok": False,
            "message": "部分文件未成功写入",
        }

    # ----- real extraction helpers -----

    @staticmethod
    def _extract_pdf(source: str) -> tuple[str, str, str]:
        """从 PDF 文件中提取文本。支持本地路径。"""
        import pdfplumber

        path = Path(source)
        if not path.exists():
            return f"[PDF 文件不存在: {source}]", path.stem, ""

        pages_text: list[str] = []
        try:
            with pdfplumber.open(str(path)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        pages_text.append(page_text)
        except Exception as e:
            return f"[PDF 提取失败: {e}]", path.stem, ""

        text = "\n\n".join(pages_text)
        return text, path.stem, ""

    @staticmethod
    def _extract_epub(source: str) -> tuple[str, str, str]:
        """从 EPUB 文件中提取文本。"""
        import ebooklib
        from ebooklib import epub
        from html.parser import HTMLParser

        class _TextExtractor(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self._parts: list[str] = []
            def handle_data(self, data: str) -> None:
                self._parts.append(data)
            def get_text(self) -> str:
                return " ".join(self._parts)

        path = Path(source)
        if not path.exists():
            return f"[EPUB 文件不存在: {source}]", path.stem, ""

        try:
            book = epub.read_epub(str(path))
        except Exception as e:
            return f"[EPUB 读取失败: {e}]", path.stem, ""

        # 提取标题和作者
        title = book.get_metadata("DC", "title")
        title = title[0][0] if title else path.stem
        author = book.get_metadata("DC", "author")
        author = author[0][0] if author else ""

        # 提取正文
        chapters: list[str] = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            html_content = item.get_content().decode("utf-8", errors="ignore")
            extractor = _TextExtractor()
            extractor.feed(html_content)
            chapter_text = extractor.get_text().strip()
            if chapter_text:
                chapters.append(chapter_text)

        text = "\n\n".join(chapters)
        return text, title, author

    @staticmethod
    async def _extract_url(source: str) -> tuple[str, str]:
        """从 URL 提取网页正文。"""
        import httpx
        from readability import Document

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(source, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; IntelliTutor/1.0)",
                })
                resp.raise_for_status()
        except Exception as e:
            return f"[URL 获取失败: {e}]", source

        try:
            doc = Document(resp.text)
            title = doc.title()
            # readability 提取正文 HTML，再简单去标签
            import re
            summary_html = doc.summary()
            text = re.sub(r"<[^>]+>", " ", summary_html)
            text = re.sub(r"\s+", " ", text).strip()
            return text, title
        except Exception as e:
            return f"[URL 解析失败: {e}]", source
