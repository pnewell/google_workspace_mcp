"""
Tests for surfacing per-paragraph indices inside containers
(table cells, headers, footers, footnotes) from inspect_doc_structure.
"""

import json
from unittest.mock import Mock

import pytest

from gdocs import docs_tools


def _unwrap(tool):
    fn = tool.fn if hasattr(tool, "fn") else tool
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def _paragraph_element(start, end, text):
    return {
        "startIndex": start,
        "endIndex": end,
        "paragraph": {
            "elements": [
                {
                    "startIndex": start,
                    "endIndex": end,
                    "textRun": {"content": text},
                }
            ]
        },
    }


def _table_element(start, end, rows, columns, cell_factory):
    table_rows = []
    for row_idx in range(rows):
        cells = []
        for col_idx in range(columns):
            cells.append(cell_factory(row_idx, col_idx))
        table_rows.append({"tableCells": cells})
    return {
        "startIndex": start,
        "endIndex": end,
        "table": {"tableRows": table_rows},
    }


def _simple_cell(start, end, text):
    return {
        "startIndex": start,
        "endIndex": end,
        "content": [_paragraph_element(start + 1, end - 1, text)],
    }


class TestInspectDocStructureFootnotes:
    @pytest.mark.asyncio
    async def test_single_footnote_surfaces_segment_with_elements(self):
        service = Mock()
        service.documents.return_value.get.return_value.execute.return_value = {
            "title": "Footnoted",
            "body": {"content": [_paragraph_element(1, 10, "Body\n")]},
            "headers": {},
            "footers": {},
            "footnotes": {
                "kix.ft1": {
                    "content": [_paragraph_element(2, 11, "Footnote text\n")],
                }
            },
            "tabs": [],
            "namedRanges": {},
        }

        result = await _unwrap(docs_tools.inspect_doc_structure)(
            service=service,
            user_google_email="user@example.com",
            document_id="d" * 25,
            detailed=True,
        )

        parsed = json.loads(result.split("\n\n", 1)[1].rsplit("\n\nLink:", 1)[0])

        assert "footnotes" in parsed
        entry = parsed["footnotes"]["kix.ft1"]
        assert entry["segment_id"] == "kix.ft1"
        assert entry["start_index"] == 2
        assert entry["end_index"] == 11
        assert entry["content_preview"] == "Footnote text\n"
        assert entry["element_count"] == 1
        assert len(entry["elements"]) == 1
        assert entry["elements"][0]["type"] == "paragraph"
        assert entry["elements"][0]["text_preview"] == "Footnote text\n"

    @pytest.mark.asyncio
    async def test_zero_footnotes_omits_key(self):
        service = Mock()
        service.documents.return_value.get.return_value.execute.return_value = {
            "title": "No Footnotes",
            "body": {"content": [_paragraph_element(1, 10, "Body\n")]},
            "headers": {},
            "footers": {},
            "tabs": [],
            "namedRanges": {},
        }

        result = await _unwrap(docs_tools.inspect_doc_structure)(
            service=service,
            user_google_email="user@example.com",
            document_id="e" * 25,
            detailed=True,
        )

        parsed = json.loads(result.split("\n\n", 1)[1].rsplit("\n\nLink:", 1)[0])
        assert "footnotes" not in parsed

    @pytest.mark.asyncio
    async def test_multi_paragraph_footnote_surfaces_each_paragraph(self):
        service = Mock()
        service.documents.return_value.get.return_value.execute.return_value = {
            "title": "Long Footnote",
            "body": {"content": [_paragraph_element(1, 10, "Body\n")]},
            "headers": {},
            "footers": {},
            "footnotes": {
                "kix.ft2": {
                    "content": [
                        _paragraph_element(2, 11, "First\n"),
                        _paragraph_element(11, 20, "Second\n"),
                    ]
                }
            },
            "tabs": [],
            "namedRanges": {},
        }

        result = await _unwrap(docs_tools.inspect_doc_structure)(
            service=service,
            user_google_email="user@example.com",
            document_id="f" * 25,
            detailed=True,
        )

        parsed = json.loads(result.split("\n\n", 1)[1].rsplit("\n\nLink:", 1)[0])

        entry = parsed["footnotes"]["kix.ft2"]
        assert entry["element_count"] == 2
        previews = [el["text_preview"] for el in entry["elements"]]
        assert previews == ["First\n", "Second\n"]


class TestInspectDocStructureContainerIntegration:
    @pytest.mark.asyncio
    async def test_tables_headers_footers_and_footnote_all_expose_elements(self):
        service = Mock()
        service.documents.return_value.get.return_value.execute.return_value = {
            "title": "Full Doc",
            "body": {
                "content": [
                    _paragraph_element(1, 15, "Body paragraph\n"),
                    _table_element(
                        15,
                        80,
                        rows=2,
                        columns=2,
                        cell_factory=lambda r, c: _simple_cell(
                            15 + r * 16 + c * 8,
                            21 + r * 16 + c * 8,
                            f"r{r}c{c}",
                        ),
                    ),
                ]
            },
            "headers": {
                "hdr-1": {
                    "content": [
                        _paragraph_element(0, 6, "HeadA\n"),
                        _paragraph_element(6, 12, "HeadB\n"),
                    ]
                }
            },
            "footers": {
                "ftr-1": {
                    "content": [_paragraph_element(0, 9, "Footing\n")],
                }
            },
            "footnotes": {
                "kix.ft1": {
                    "content": [_paragraph_element(2, 11, "Footnote\n")],
                }
            },
            "tabs": [],
            "namedRanges": {},
        }

        result = await _unwrap(docs_tools.inspect_doc_structure)(
            service=service,
            user_google_email="user@example.com",
            document_id="g" * 25,
            detailed=True,
        )

        parsed = json.loads(result.split("\n\n", 1)[1].rsplit("\n\nLink:", 1)[0])

        table_entry = parsed["tables"][0]
        assert table_entry["dimensions"] == {"rows": 2, "columns": 2}
        assert len(table_entry["cells"]) == 4
        top_left = table_entry["cells"][0]
        assert top_left["row"] == 0
        assert top_left["column"] == 0
        assert top_left["start_index"] == 15
        assert top_left["end_index"] == 21
        assert top_left["elements"][0]["type"] == "paragraph"
        assert top_left["elements"][0]["text_preview"] == "r0c0"

        header_entries = parsed["headers"]
        assert header_entries[0]["segment_id"] == "hdr-1"
        assert header_entries[0]["source"] == "segment_content"
        header_previews = [el["text_preview"] for el in header_entries[0]["elements"]]
        assert header_previews == ["HeadA\n", "HeadB\n"]

        footer_entries = parsed["footers"]
        assert footer_entries[0]["segment_id"] == "ftr-1"
        assert footer_entries[0]["source"] == "segment_content"
        assert footer_entries[0]["elements"][0]["text_preview"] == "Footing\n"

        footnote_entry = parsed["footnotes"]["kix.ft1"]
        assert footnote_entry["segment_id"] == "kix.ft1"
        assert footnote_entry["elements"][0]["text_preview"] == "Footnote\n"

    @pytest.mark.asyncio
    async def test_documentstyle_sourced_header_has_empty_elements_list(self):
        service = Mock()
        service.documents.return_value.get.return_value.execute.return_value = {
            "title": "Style Only",
            "body": {"content": []},
            "headers": {},
            "footers": {},
            "documentStyle": {
                "defaultHeaderId": "hdr-style-1",
                "defaultFooterId": "ftr-style-1",
            },
            "tabs": [],
            "namedRanges": {},
        }

        result = await _unwrap(docs_tools.inspect_doc_structure)(
            service=service,
            user_google_email="user@example.com",
            document_id="h" * 25,
            detailed=True,
        )

        parsed = json.loads(result.split("\n\n", 1)[1].rsplit("\n\nLink:", 1)[0])

        header_entry = parsed["headers"][0]
        assert header_entry["source"] == "documentStyle.defaultHeaderId"
        assert header_entry["elements"] == []

        footer_entry = parsed["footers"][0]
        assert footer_entry["source"] == "documentStyle.defaultFooterId"
        assert footer_entry["elements"] == []

    @pytest.mark.asyncio
    async def test_nested_table_inside_cell_surfaces_recursive_elements(self):
        inner_table = _table_element(
            21,
            45,
            rows=1,
            columns=2,
            cell_factory=lambda r, c: _simple_cell(
                21 + c * 10,
                30 + c * 10,
                f"inner{c}",
            ),
        )
        outer_cell = {
            "startIndex": 20,
            "endIndex": 50,
            "content": [inner_table, _paragraph_element(46, 50, "tail")],
        }
        outer_table = {
            "startIndex": 15,
            "endIndex": 55,
            "table": {"tableRows": [{"tableCells": [outer_cell]}]},
        }

        service = Mock()
        service.documents.return_value.get.return_value.execute.return_value = {
            "title": "Nested",
            "body": {
                "content": [
                    _paragraph_element(1, 14, "Body\n"),
                    outer_table,
                ]
            },
            "headers": {},
            "footers": {},
            "tabs": [],
            "namedRanges": {},
        }

        result = await _unwrap(docs_tools.inspect_doc_structure)(
            service=service,
            user_google_email="user@example.com",
            document_id="n" * 25,
            detailed=True,
        )

        parsed = json.loads(result.split("\n\n", 1)[1].rsplit("\n\nLink:", 1)[0])

        outer_cell_summary = parsed["tables"][0]["cells"][0]
        assert len(outer_cell_summary["elements"]) == 2

        nested_table_summary = outer_cell_summary["elements"][0]
        assert nested_table_summary["type"] == "table"
        assert nested_table_summary["rows"] == 1
        assert nested_table_summary["columns"] == 2
        assert nested_table_summary["cell_count"] == 2
        assert nested_table_summary["cells"][0]["elements"][0]["text_preview"] == (
            "inner0"
        )

        tail_paragraph = outer_cell_summary["elements"][1]
        assert tail_paragraph["type"] == "paragraph"
        assert tail_paragraph["text_preview"] == "tail"


class TestGetParagraphStartIndicesInRange:
    """Verify paragraph-start lookup walks into table cells."""

    @pytest.mark.asyncio
    async def test_returns_cell_paragraph_starts(self):
        from gdocs.docs_helpers import get_paragraph_start_indices_in_range

        body = {
            "content": [
                _paragraph_element(1, 10, "Top\n"),
                _table_element(
                    10,
                    60,
                    rows=1,
                    columns=2,
                    cell_factory=lambda r, c: _simple_cell(
                        11 + c * 20, 30 + c * 20, f"cell{c}\n"
                    ),
                ),
            ]
        }
        service = Mock()
        service.documents.return_value.get.return_value.execute.return_value = {
            "body": body,
        }

        result = await get_paragraph_start_indices_in_range(
            service, "doc123", 1, 60
        )

        assert 1 in result
        assert 12 in result
        assert 32 in result
        assert len(result) == 3
