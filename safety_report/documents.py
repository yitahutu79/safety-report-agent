"""本地资料解析；每一个证据块保留文件哈希和可定位的出处。"""
import csv
import hashlib
import io
import json
import math
import re
import uuid
from collections import defaultdict
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NS = {"w": W[1:-1]}


def text_of(node):
    return "".join(e.text or "" for e in node.iter(W + "t")).strip()


def read_docx(path):
    """遍历正文、表格、嵌套表格；不把目录条目误识别为正文章节。"""
    with zipfile.ZipFile(path) as archive:
        if sum(e.file_size for e in archive.infolist()) > 350_000_000:
            raise ValueError("Word 解压后超过 350 MB，请拆分资料")
        root = ET.fromstring(archive.read("word/document.xml"))
        styles = {}
        if "word/styles.xml" in archive.namelist():
            for style in ET.fromstring(archive.read("word/styles.xml")).findall("w:style", NS):
                name = style.find("w:name", NS)
                level = style.find("w:pPr/w:outlineLvl", NS)
                styles[style.get(W + "styleId")] = {
                    "name": name.get(W + "val", "") if name is not None else "",
                    "level": int(level.get(W + "val")) + 1 if level is not None else None,
                }
        blocks = []
        for index, element in enumerate(root.find("w:body", NS)):
            if element.tag == W + "p":
                text = text_of(element)
                if not text:
                    continue
                sid = element.find("w:pPr/w:pStyle", NS)
                sid = sid.get(W + "val") if sid is not None else ""
                style = styles.get(sid, {})
                level = element.find("w:pPr/w:outlineLvl", NS)
                blocks.append({"kind": "paragraph", "locator": f"body[{index}]",
                               "text": text, "style_id": sid, "style_name": style.get("name", ""),
                               "level": int(level.get(W + "val")) + 1 if level is not None else style.get("level")})
            elif element.tag == W + "tbl":
                rows = [[text_of(cell) for cell in row.findall("w:tc", NS)]
                        for row in element.findall("w:tr", NS)]
                blocks.append({"kind": "table", "locator": f"body[{index}]", "rows": rows,
                               "text": "\n".join(" | ".join(row) for row in rows)})
        sections = []
        for section in root.findall(".//w:sectPr", NS):
            sections.append({child.tag.split("}")[-1]: {k.split("}")[-1]: v for k, v in child.attrib.items()}
                             for child in section if child.tag in {W + "pgSz", W + "pgMar"}})
        return blocks, {"image_resources": len([n for n in archive.namelist() if n.startswith("word/media/")]),
                        "sections": sections}


def inspect_template(path):
    blocks, info = read_docx(path)
    headings, tables, captions, attachments = [], [], [], []
    last_caption = ""
    for block in blocks:
        text = block["text"]
        if block["kind"] == "paragraph":
            if block["level"] and block["level"] <= 3 and re.match(r"^[1-7](?:\.\d+)*\s*[^\d.]", text):
                headings.append({k: block[k] for k in ("text", "level", "locator", "style_id")})
            if re.match(r"^[图表]\s*\d", text):
                last_caption = text
                captions.append({"text": text, "locator": block["locator"]})
            if re.match(r"^附[件图]\s*\d", text):
                attachments.append({"text": text, "locator": block["locator"]})
        else:
            tables.append({"caption": last_caption, "locator": block["locator"],
                           "row_count": len(block["rows"]), "headers": block["rows"][0] if block["rows"] else []})
            last_caption = ""
    return {"reference_path": str(Path(path).resolve()), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "block_count": len(blocks), "table_count": len(tables), **info,
            "headings": headings, "tables": tables, "captions": captions, "attachments": attachments,
            "notes": ["页数必须经渲染确认，未采用 Word 缓存页数", "这是已完成项目样例，不是可以直接替换公司名的空白模板",
                      "仅作结构和格式参考，原项目事实与规范引用不能自动沿用"]}


def parse_file(path):
    path = Path(path)
    suffix = path.suffix.lower()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    warnings = []
    if suffix == ".docx":
        blocks, _ = read_docx(path)
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF 解析依赖未安装；请使用 Docker 版本或安装 requirements.txt") from exc
        blocks = []
        for i, page in enumerate(PdfReader(path).pages, 1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                # A broken or overly complex page must not discard readable pages.
                warnings.append(f"第 {i} 页文本提取失败（{type(exc).__name__}），请检查原图或使用 OCR")
                continue
            if len(text.strip()) < 30:
                warnings.append(f"第 {i} 页缺少文本层，需要 OCR 或图纸人工核对")
            if text.strip():
                blocks.append({"kind": "paragraph", "text": text.strip(), "locator": f"page[{i}]"})
    elif suffix == ".csv":
        rows = list(csv.reader(io.StringIO(decode(path.read_bytes()))))
        blocks = [{"kind": "table", "rows": rows, "text": "\n".join(" | ".join(r) for r in rows), "locator": "csv[1]"}]
    elif suffix in {".txt", ".md", ".json"}:
        blocks = [{"kind": "paragraph", "text": p.strip(), "locator": f"paragraph[{i}]"}
                  for i, p in enumerate(re.split(r"\n\s*\n", decode(path.read_bytes())), 1) if p.strip()]
    else:
        raise ValueError("此格式暂不支持自动读取；旧版 .doc 请另存为 .docx；扫描件、图片和 CAD 图纸需要 OCR/图纸识别模块")
    chunks = []
    for block in blocks:
        # 固定重叠窗口仅用于检索；结构化表格仍保留在原始 blocks 中。
        for offset in range(0, len(block["text"]), 1800):
            text = block["text"][offset:offset + 2200]
            evidence_id = hashlib.sha256(f"{digest}:{block['locator']}:{offset}".encode()).hexdigest()[:20]
            chunks.append({"id": evidence_id, "source": path.name, "sha256": digest,
                           "locator": block["locator"], "offset": offset, "kind": block["kind"], "text": text})
    return {"file": path.name, "sha256": digest, "blocks": blocks, "chunks": chunks, "warnings": warnings}


def decode(data):
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError("无法识别文本编码，请转成 UTF-8")


def tokens(text):
    text = re.sub(r"\s+", "", text.lower())
    return set(re.findall(r"[a-z0-9_]+", text)) | {text[i:i + 2] for i in range(len(text) - 1)}


def retrieve(chunks, query, limit=10):
    query_tokens = tokens(query)
    ranked = sorted(chunks, key=lambda c: len(query_tokens & tokens(c["text"])), reverse=True)
    # 过滤零相关结果，不能拿任意材料凑满检索数量。
    return [c for c in ranked if query_tokens & tokens(c["text"])][:limit]


class EvidenceIndex:
    """一次建立倒排索引，避免为每个小节反复扫描上千个长段落。"""
    def __init__(self, chunks):
        self.chunks = chunks
        self.postings = defaultdict(list)
        for index, chunk in enumerate(chunks):
            for token in tokens(chunk['text']):
                self.postings[token].append(index)

    def search(self, query, limit=10):
        scores = defaultdict(float)
        for token in tokens(query):
            matches = self.postings.get(token, ())
            weight = 1 + math.log((len(self.chunks) + 1) / (len(matches) + 1))
            for index in matches:
                scores[index] += weight
        # GPT Researcher's BM25 ranks the existing keyword candidates locally.
        # Keep the zero-overlap filter and corpus boundary; never fetch external data.
        from .gptr_bm25 import bm25_scores
        candidates = sorted(scores, key=scores.get, reverse=True)
        lexical = bm25_scores(tokens(query), [tokens(self.chunks[i]['text']) for i in candidates])
        ranked = sorted(range(len(candidates)), key=lambda i: (-lexical[i], i))
        return [self.chunks[candidates[i]] for i in ranked[:limit]]


class HybridEvidenceIndex(EvidenceIndex):
    """中文关键词检索 + Qdrant/FastEmbed 语义检索，使用 RRF 融合排序。

    没有配置持久化索引或依赖不可用时退回本地关键词检索；模型首次下载失败
    时保留报告生成能力，并将其作为可见警告写入日志，而不是伪装成已做语义检索。
    """
    MODEL = "BAAI/bge-small-zh-v1.5"

    def __init__(self, chunks, path=None, rebuild=False):
        super().__init__(chunks)
        self.client = None
        self.point_ids = {str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["id"])): chunk["id"] for chunk in chunks}
        self.by_id = {chunk["id"]: chunk for chunk in chunks}
        self.semantic_error = ""
        if path and chunks:
            try:
                from qdrant_client import QdrantClient, models
                self.client = QdrantClient(path=str(path))
                self.models = models
                self.collection = "project_evidence"
                collection_exists = self.client.collection_exists(self.collection)
                exists = collection_exists
                if collection_exists:
                    info = self.client.get_collection(self.collection)
                    exists = (info.points_count or 0) == len(chunks)
                if collection_exists and (rebuild or not exists):
                    self.client.delete_collection(self.collection)
                    exists = False
                if not exists:
                    self.client.create_collection(self.collection, vectors_config=models.VectorParams(
                        size=self.client.get_embedding_size(self.MODEL), distance=models.Distance.COSINE))
                    self.client.upload_collection(self.collection,
                        vectors=[models.Document(text=c["text"], model=self.MODEL) for c in chunks],
                        ids=[str(uuid.uuid5(uuid.NAMESPACE_URL, c["id"])) for c in chunks],
                        payload=[{"evidence_id": c["id"]} for c in chunks])
            except Exception as exc:
                self.semantic_error = str(exc)[:400]
                self.close()
                if self.client:
                    self.client.close()
                self.client = None

    def search(self, query, limit=10):
        lexical = super().search(query, max(limit * 3, 20))
        semantic = []
        if self.client:
            try:
                points = self.client.query_points(self.collection,
                    query=self.models.Document(text=query, model=self.MODEL), limit=max(limit * 3, 20)).points
                semantic = [self.by_id[self.point_ids[str(point.id)]] for point in points if str(point.id) in self.point_ids]
            except Exception as exc:
                self.semantic_error = str(exc)[:400]
        # Reciprocal Rank Fusion 让语义近似和精确法规/参数词都能进入候选集。
        scores = defaultdict(float)
        for ranked in (lexical, semantic):
            for rank, chunk in enumerate(ranked, 1):
                scores[chunk["id"]] += 1 / (60 + rank)
        return [self.by_id[eid] for eid in sorted(scores, key=scores.get, reverse=True)[:limit]]

    def close(self):
        if self.client:
            self.client.close()
            self.client = None

    def __del__(self):
        self.close()
