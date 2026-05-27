"""
Tests for the create_footnote operation in batch_update_doc.

Covers helper construction, validate_operation, batch manager integration.
"""

from unittest.mock import Mock

import pytest

from gdocs.docs_helpers import (
    create_create_footnote_request,
    validate_operation,
)


class TestCreateCreateFootnoteRequest:
    def test_with_index(self):
        result = create_create_footnote_request(10)
        assert result == {"createFootnote": {"location": {"index": 10}}}

    def test_end_of_segment(self):
        result = create_create_footnote_request(None, end_of_segment=True)
        assert result == {"createFootnote": {"endOfSegmentLocation": {}}}

    def test_with_tab_id(self):
        result = create_create_footnote_request(5, tab_id="t.abc")
        assert result == {
            "createFootnote": {"location": {"index": 5, "tabId": "t.abc"}}
        }


class TestValidateOperation:
    def test_rejects_both_index_and_end_of_segment(self):
        is_valid, msg = validate_operation(
            {"type": "create_footnote", "index": 5, "end_of_segment": True}
        )
        assert not is_valid
        assert "Cannot specify both" in msg

    def test_rejects_neither_index_nor_end_of_segment(self):
        is_valid, msg = validate_operation({"type": "create_footnote"})
        assert not is_valid
        assert "index" in msg


class TestBatchManagerIntegration:
    @pytest.fixture()
    def manager(self):
        from gdocs.managers.batch_operation_manager import BatchOperationManager

        return BatchOperationManager(Mock())

    def test_build_create_footnote_through_dispatch(self, manager):
        request, desc = manager._build_operation_request(
            {"type": "create_footnote", "index": 12},
            "create_footnote",
        )
        assert request == {"createFootnote": {"location": {"index": 12}}}
        assert "create footnote at 12" in desc
