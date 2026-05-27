from unittest.mock import AsyncMock, Mock, patch

import pytest

from gdocs.list_span_compiler import ListParagraph
from gdocs.managers.batch_operation_manager import BatchOperationManager

LINES = [
    ("BOLD_TOP_LEVEL\n", 1, 16),
    ("PLAIN_TOP_LEVEL\n", 16, 32),
    ("ITALIC_NESTED\n", 32, 47),
    ("STRIKE_DEEP_NEST\n", 47, 64),
]


def _mock_paragraphs() -> list[ListParagraph]:
    return [
        ListParagraph(start, end, text, None, None) for text, start, end in LINES
    ]


def _range_of(requests: list[dict], key: str) -> list[dict]:
    return [r[key]["range"] for r in requests if key in r]


@pytest.fixture()
def manager() -> BatchOperationManager:
    return BatchOperationManager(Mock())


@pytest.mark.asyncio
async def test_interleaved_format_and_bullet_ops_preserve_indices(manager):
    operations = [
        {
            "type": "format_text",
            "start_index": 1,
            "end_index": 15,
            "bold": True,
        },
        {
            "type": "create_bullet_list",
            "start_index": 1,
            "end_index": 32,
        },
        {
            "type": "format_text",
            "start_index": 32,
            "end_index": 46,
            "italic": True,
        },
        {
            "type": "create_bullet_list",
            "start_index": 32,
            "end_index": 47,
            "nesting_level": 1,
        },
        {
            "type": "format_text",
            "start_index": 16,
            "end_index": 31,
            "underline": True,
        },
        {
            "type": "create_bullet_list",
            "start_index": 47,
            "end_index": 64,
            "nesting_level": 2,
        },
        {
            "type": "format_text",
            "start_index": 47,
            "end_index": 63,
            "strikethrough": True,
        },
    ]

    with patch(
        "gdocs.managers.batch_operation_manager.fetch_list_paragraphs",
        new=AsyncMock(return_value=_mock_paragraphs()),
    ):
        requests, descriptions = await manager._validate_and_build_requests(
            operations, document_id="d" * 25
        )

    assert len(descriptions) == len(operations)

    text_style_ranges = _range_of(requests, "updateTextStyle")
    assert text_style_ranges == [
        {"startIndex": 1, "endIndex": 15},
        {"startIndex": 32, "endIndex": 46},
        {"startIndex": 16, "endIndex": 31},
        {"startIndex": 47, "endIndex": 63},
    ]

    bold = requests[0]["updateTextStyle"]["textStyle"]
    assert bold.get("bold") is True

    italic = next(
        r["updateTextStyle"]["textStyle"]
        for r in requests
        if r.get("updateTextStyle", {}).get("range") == {"startIndex": 32, "endIndex": 46}
    )
    assert italic.get("italic") is True

    underline = next(
        r["updateTextStyle"]["textStyle"]
        for r in requests
        if r.get("updateTextStyle", {}).get("range") == {"startIndex": 16, "endIndex": 31}
    )
    assert underline.get("underline") is True

    strike = next(
        r["updateTextStyle"]["textStyle"]
        for r in requests
        if r.get("updateTextStyle", {}).get("range") == {"startIndex": 47, "endIndex": 63}
    )
    assert strike.get("strikethrough") is True

    bullet_creates = _range_of(requests, "createParagraphBullets")
    assert [r["startIndex"] for r in bullet_creates] == [1, 1, 1]
    assert bullet_creates[0]["endIndex"] == 32
    assert bullet_creates[1]["endIndex"] == 48
    assert bullet_creates[2]["endIndex"] == 67

    type_order = [next(iter(r)) for r in requests]

    def bullet_block_index(after: int = -1) -> int:
        for i in range(after + 1, len(type_order)):
            if type_order[i] == "deleteParagraphBullets":
                return i
            if type_order[i] == "createParagraphBullets" and (
                i == 0 or type_order[i - 1] != "insertText"
            ):
                return i
        raise AssertionError("no bullet rebuild block found")

    bold_idx = type_order.index("updateTextStyle")
    first_bullet_idx = bullet_block_index()
    italic_idx = type_order.index("updateTextStyle", bold_idx + 1)
    second_bullet_idx = bullet_block_index(first_bullet_idx)
    underline_idx = type_order.index("updateTextStyle", italic_idx + 1)
    third_bullet_idx = bullet_block_index(second_bullet_idx)
    strike_idx = type_order.index("updateTextStyle", underline_idx + 1)

    assert bold_idx < first_bullet_idx < italic_idx < second_bullet_idx
    assert underline_idx < third_bullet_idx < strike_idx


@pytest.mark.asyncio
async def test_execute_interleaved_batch_single_api_call(manager):
    operations = [
        {"type": "format_text", "start_index": 1, "end_index": 15, "bold": True},
        {"type": "create_bullet_list", "start_index": 1, "end_index": 32},
        {"type": "format_text", "start_index": 32, "end_index": 46, "italic": True},
        {"type": "create_bullet_list", "start_index": 32, "end_index": 47, "nesting_level": 1},
    ]

    manager._execute_batch_requests = AsyncMock(return_value={"replies": [{}]})

    with patch(
        "gdocs.managers.batch_operation_manager.fetch_list_paragraphs",
        new=AsyncMock(return_value=_mock_paragraphs()),
    ):
        success, message, meta = await manager.execute_batch_operations(
            "d" * 25, operations
        )

    assert success, message
    assert meta["operations_count"] == 4
    assert meta["requests_count"] > meta["operations_count"]

    batch_requests = manager._execute_batch_requests.call_args[0][1]
    assert manager._execute_batch_requests.call_count == 1
    assert any("updateTextStyle" in r for r in batch_requests)
    assert any("createParagraphBullets" in r for r in batch_requests)
