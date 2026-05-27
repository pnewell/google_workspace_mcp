from unittest.mock import AsyncMock, Mock, patch

import pytest

from gdocs.list_span_compiler import ListParagraph
from gdocs.managers.batch_operation_manager import BatchOperationManager

CELL_LINES = [
    ("BOLD_TOP_LEVEL\n", 5, 20),
    ("PLAIN_TOP_LEVEL\n", 20, 36),
    ("ITALIC_NESTED\n", 36, 50),
    ("STRIKE_DEEP_NEST\n", 50, 67),
]


def _cell_paragraphs() -> list[ListParagraph]:
    return [
        ListParagraph(start, end, text, None, None) for text, start, end in CELL_LINES
    ]


@pytest.fixture()
def manager() -> BatchOperationManager:
    return BatchOperationManager(Mock())


@pytest.mark.asyncio
async def test_interleaved_cell_batch_uses_fast_path_on_first_bullet(manager):
    operations = [
        {"type": "format_text", "start_index": 5, "end_index": 19, "bold": True},
        {"type": "create_bullet_list", "start_index": 5, "end_index": 36},
        {"type": "format_text", "start_index": 36, "end_index": 49, "italic": True},
        {
            "type": "create_bullet_list",
            "start_index": 36,
            "end_index": 50,
            "nesting_level": 1,
        },
    ]

    with patch(
        "gdocs.managers.batch_operation_manager.fetch_list_paragraphs",
        new=AsyncMock(return_value=_cell_paragraphs()),
    ):
        requests, descriptions = await manager._validate_and_build_requests(
            operations, document_id="d" * 25
        )

    assert len(descriptions) == 4
    type_order = [next(iter(r)) for r in requests]
    assert type_order[0] == "updateTextStyle"
    assert type_order[1] == "createParagraphBullets"
    assert "deleteParagraphBullets" not in type_order[:2]

    bullet_creates = [
        r["createParagraphBullets"]["range"]
        for r in requests
        if "createParagraphBullets" in r
    ]
    assert bullet_creates[0] == {"startIndex": 5, "endIndex": 36}
    assert bullet_creates[1]["startIndex"] == 5

    deletes = [
        r["deleteParagraphBullets"]["range"]
        for r in requests
        if "deleteParagraphBullets" in r
    ]
    assert deletes == [{"startIndex": 5, "endIndex": 36}]
