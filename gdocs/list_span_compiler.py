"""Compile create_bullet_list ops into list-span rebuild requests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from gdocs.docs_helpers import (
    VALID_BULLET_PRESETS,
    _build_range,
    create_delete_bullet_list_request,
    create_delete_range_request,
    create_insert_text_request,
    create_update_paragraph_style_request,
)

_PARAGRAPH_FIELDS = (
    "startIndex,endIndex,"
    "paragraph(bullet,elements(textRun(content)))"
)
_TABLE_FIELDS = (
    f"table(tableRows(tableCells(content({_PARAGRAPH_FIELDS},"
    f"table(tableRows(tableCells(content({_PARAGRAPH_FIELDS}))))))))"
)
_CONTENT_FIELDS = f"content({_PARAGRAPH_FIELDS},{_TABLE_FIELDS})"


@dataclass(frozen=True)
class ListParagraph:
    start: int
    end: int
    text: str
    list_id: str | None
    nesting_level: int | None

    @property
    def stripped(self) -> str:
        return self.text.strip()

    @property
    def leading_tabs(self) -> int:
        return len(self.text) - len(self.text.lstrip("\t"))


@dataclass(frozen=True)
class BulletOp:
    start_index: int
    end_index: int
    depth: int


def resolve_bullet_preset(
    list_type: str, bullet_preset: Optional[str] = None
) -> str:
    if bullet_preset is not None:
        if bullet_preset not in VALID_BULLET_PRESETS:
            raise ValueError(
                f"bullet_preset must be one of: {', '.join(VALID_BULLET_PRESETS)}"
            )
        return bullet_preset
    if list_type == "UNORDERED":
        return "BULLET_DISC_CIRCLE_SQUARE"
    if list_type == "CHECKBOX":
        return "BULLET_CHECKBOX"
    return "NUMBERED_DECIMAL_ALPHA_ROMAN"


def norm_depth(level: int | None) -> int:
    return 0 if level is None else level


def _is_listed_paragraph(paragraph: ListParagraph) -> bool:
    return bool(paragraph.list_id)


def _listed_contiguous_ranges(span: list[ListParagraph]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    i = 0
    while i < len(span):
        if not _is_listed_paragraph(span[i]):
            i += 1
            continue
        start = span[i].start
        end = span[i].end
        j = i + 1
        while j < len(span) and _is_listed_paragraph(span[j]):
            end = span[j].end
            j += 1
        ranges.append((start, end))
        i = j
    return ranges


def parse_paragraphs_from_content(content: list[dict[str, Any]]) -> list[ListParagraph]:
    out: list[ListParagraph] = []

    def walk(elements: list[dict[str, Any]]) -> None:
        if not isinstance(elements, list):
            return
        for el in elements:
            if "paragraph" in el:
                text = "".join(
                    run.get("textRun", {}).get("content", "")
                    for run in el["paragraph"].get("elements", [])
                )
                if not text.strip():
                    continue
                bullet = el["paragraph"].get("bullet") or {}
                out.append(
                    ListParagraph(
                        start=el["startIndex"],
                        end=el["endIndex"],
                        text=text,
                        list_id=bullet.get("listId"),
                        nesting_level=bullet.get("nestingLevel"),
                    )
                )
            elif "table" in el:
                for row in el["table"].get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        walk(cell.get("content", []))

    walk(content)
    return out


async def fetch_list_paragraphs(
    service: Any,
    document_id: str,
    tab_id: Optional[str] = None,
    segment_id: Optional[str] = None,
) -> list[ListParagraph]:
    if segment_id:
        fields = f"headers/{segment_id}({_CONTENT_FIELDS}),footers/{segment_id}({_CONTENT_FIELDS})"
        doc_data = await asyncio.to_thread(
            service.documents().get(documentId=document_id, fields=fields).execute
        )
        header = doc_data.get("headers", {}).get(segment_id, {})
        footer = doc_data.get("footers", {}).get(segment_id, {})
        content = header.get("content") or footer.get("content") or []
        return parse_paragraphs_from_content(content)

    if tab_id:
        fields = f"tabs(tabProperties(tabId),documentTab(body({_CONTENT_FIELDS})))"
        doc_data = await asyncio.to_thread(
            service.documents()
            .get(documentId=document_id, includeTabsContent=True, fields=fields)
            .execute
        )
        for tab in doc_data.get("tabs", []):
            if tab.get("tabProperties", {}).get("tabId") == tab_id:
                body = tab.get("documentTab", {}).get("body", {})
                return parse_paragraphs_from_content(body.get("content", []))
        return []

    doc_data = await asyncio.to_thread(
        service.documents()
        .get(documentId=document_id, fields=f"body({_CONTENT_FIELDS})")
        .execute
    )
    return parse_paragraphs_from_content(doc_data.get("body", {}).get("content", []))


def paragraphs_in_range(
    paras: list[ListParagraph], start: int, end: int
) -> list[ListParagraph]:
    return [p for p in paras if p.start >= start and p.start < end]


def resolve_list_span(paras: list[ListParagraph], op: BulletOp) -> list[ListParagraph]:
    touched_idxs = [
        i
        for i, p in enumerate(paras)
        if p.start >= op.start_index and p.start < op.end_index
    ]
    if not touched_idxs:
        raise ValueError(f"No paragraphs in range {op.start_index}-{op.end_index}")

    lo, hi = min(touched_idxs), max(touched_idxs)

    list_ids: set[str] = set()
    for i in touched_idxs:
        if paras[i].list_id:
            list_ids.add(paras[i].list_id)
        if i > 0 and paras[i - 1].list_id:
            list_ids.add(paras[i - 1].list_id)
        if i + 1 < len(paras) and paras[i + 1].list_id:
            list_ids.add(paras[i + 1].list_id)

    if list_ids:
        while lo > 0 and paras[lo - 1].list_id in list_ids:
            lo -= 1
        while hi + 1 < len(paras) and paras[hi + 1].list_id in list_ids:
            hi += 1

    return paras[lo : hi + 1]


def merge_depths(
    span: list[ListParagraph], op: BulletOp, prior: dict[int, int]
) -> list[int]:
    depth_by_start = {
        p.start: prior.get(p.start, norm_depth(p.nesting_level)) for p in span
    }
    for p in paragraphs_in_range(span, op.start_index, op.end_index):
        depth_by_start[p.start] = op.depth
    return [depth_by_start[p.start] for p in span]


def compile_atomic_rebuild(
    span: list[ListParagraph],
    depths: list[int],
    bullet_preset: str,
    tab_id: Optional[str] = None,
    segment_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    if len(span) != len(depths):
        raise ValueError("span/depths length mismatch")

    span_start = span[0].start
    span_end = span[-1].end
    requests: list[dict[str, Any]] = []

    listed_ranges = _listed_contiguous_ranges(span)
    for listed_start, listed_end in listed_ranges:
        requests.append(
            create_delete_bullet_list_request(
                listed_start, listed_end, tab_id, segment_id=segment_id
            )
        )
        indent_reset = create_update_paragraph_style_request(
            listed_start,
            listed_end,
            indent_start=0,
            indent_first_line=0,
            tab_id=tab_id,
            segment_id=segment_id,
        )
        if indent_reset:
            requests.append(indent_reset)

    strip_ops = [(p.start, p.start + p.leading_tabs) for p in span if p.leading_tabs]
    for start, end in sorted(strip_ops, reverse=True):
        requests.append(
            create_delete_range_request(start, end, tab_id, segment_id=segment_id)
        )

    insert_ops = [(p.start, d) for p, d in zip(span, depths) if d > 0]
    for start, depth in sorted(insert_ops, reverse=True):
        requests.append(
            create_insert_text_request(
                start, "\t" * depth, tab_id, segment_id=segment_id
            )
        )

    net = sum(d for _, d in insert_ops) - sum(e - s for s, e in strip_ops)
    requests.append(
        {
            "createParagraphBullets": {
                "range": _build_range(
                    span_start, span_end + net, tab_id, segment_id
                ),
                "bulletPreset": bullet_preset,
            }
        }
    )
    return requests


def compile_remove_list(
    span: list[ListParagraph],
    tab_id: Optional[str] = None,
    segment_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    span_start = span[0].start
    span_end = span[-1].end
    requests: list[dict[str, Any]] = [
        create_delete_bullet_list_request(
            span_start, span_end, tab_id, segment_id=segment_id
        )
    ]

    indent_reset = create_update_paragraph_style_request(
        span_start,
        span_end,
        indent_start=0,
        indent_first_line=0,
        tab_id=tab_id,
        segment_id=segment_id,
    )
    if indent_reset:
        requests.append(indent_reset)

    strip_ops = [(p.start, p.start + p.leading_tabs) for p in span if p.leading_tabs]
    for start, end in sorted(strip_ops, reverse=True):
        requests.append(
            create_delete_range_request(start, end, tab_id, segment_id=segment_id)
        )
    return requests


def virtualize_after_rebuild(
    paras: list[ListParagraph], span: list[ListParagraph], depths: list[int]
) -> list[ListParagraph]:
    span_starts = {p.start for p in span}
    depth_by_start = {p.start: d for p, d in zip(span, depths)}
    out: list[ListParagraph] = []
    for p in paras:
        if p.start in span_starts:
            depth = depth_by_start[p.start]
            out.append(
                ListParagraph(
                    p.start,
                    p.end,
                    p.text,
                    "__virtual__",
                    depth if depth else None,
                )
            )
        else:
            out.append(p)
    return out


def virtualize_after_remove(
    paras: list[ListParagraph], span: list[ListParagraph]
) -> list[ListParagraph]:
    span_starts = {p.start for p in span}
    out: list[ListParagraph] = []
    for p in paras:
        if p.start in span_starts:
            text = p.text[p.leading_tabs :]
            out.append(ListParagraph(p.start, p.end, text, None, None))
        else:
            out.append(p)
    return out


class ListSpanCompiler:
    def __init__(self) -> None:
        self._depth_by_start: dict[int, int] = {}

    def apply_op(
        self,
        paras: list[ListParagraph],
        start_index: int,
        end_index: int,
        depth: int,
        list_type: str,
        bullet_preset: Optional[str] = None,
        tab_id: Optional[str] = None,
        segment_id: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], list[ListParagraph], list[ListParagraph], list[int]]:
        preset = resolve_bullet_preset(list_type, bullet_preset)
        op = BulletOp(start_index, end_index, depth)
        span = resolve_list_span(paras, op)
        depths = merge_depths(span, op, self._depth_by_start)
        for p, d in zip(span, depths):
            self._depth_by_start[p.start] = d
        requests = compile_atomic_rebuild(
            span, depths, preset, tab_id=tab_id, segment_id=segment_id
        )
        virt = virtualize_after_rebuild(paras, span, depths)
        return requests, virt, span, depths

    def remove_op(
        self,
        paras: list[ListParagraph],
        start_index: int,
        end_index: int,
        tab_id: Optional[str] = None,
        segment_id: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], list[ListParagraph], list[ListParagraph]]:
        op = BulletOp(start_index, end_index, 0)
        span = resolve_list_span(paras, op)
        for p in span:
            self._depth_by_start.pop(p.start, None)
        requests = compile_remove_list(span, tab_id=tab_id, segment_id=segment_id)
        virt = virtualize_after_remove(paras, span)
        return requests, virt, span
