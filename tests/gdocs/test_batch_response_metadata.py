"""
Tests for BatchOperationManager._extract_response_ids and its wiring into
execute_batch_operations.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from gdocs.managers.batch_operation_manager import BatchOperationManager


def _manager() -> BatchOperationManager:
    return BatchOperationManager(service=Mock())


class TestExtractResponseIds:
    def test_extracts_create_header_reply(self):
        result = {"replies": [{"createHeader": {"headerId": "hdr-1"}}]}
        buckets = _manager()._extract_response_ids(result)
        assert buckets == {"created_headers": [{"header_id": "hdr-1"}]}

    def test_extracts_create_footer_reply(self):
        result = {"replies": [{"createFooter": {"footerId": "ftr-1"}}]}
        buckets = _manager()._extract_response_ids(result)
        assert buckets == {"created_footers": [{"footer_id": "ftr-1"}]}

    def test_extracts_create_footnote_reply(self):
        result = {"replies": [{"createFootnote": {"footnoteId": "ft-1"}}]}
        buckets = _manager()._extract_response_ids(result)
        assert buckets == {"created_footnotes": [{"footnote_id": "ft-1"}]}

    def test_mixed_replies_separate_buckets(self):
        result = {
            "replies": [
                {"createHeader": {"headerId": "hdr-1"}},
                {"insertText": {}},
                {"createFootnote": {"footnoteId": "ft-1"}},
                {"createFooter": {"footerId": "ftr-1"}},
                {"createHeader": {"headerId": "hdr-2"}},
            ]
        }
        buckets = _manager()._extract_response_ids(result)
        assert buckets == {
            "created_headers": [{"header_id": "hdr-1"}, {"header_id": "hdr-2"}],
            "created_footers": [{"footer_id": "ftr-1"}],
            "created_footnotes": [{"footnote_id": "ft-1"}],
        }


class TestExecuteBatchOperationsSurface:
    @pytest.mark.asyncio
    async def test_message_and_metadata_include_created_segment_ids(self):
        service = Mock()
        service.documents.return_value.get.return_value.execute.return_value = {
            "documentStyle": {},
            "body": {"content": []},
        }
        manager = BatchOperationManager(service=service)
        manager._execute_batch_requests = AsyncMock(
            return_value={
                "replies": [
                    {"createHeader": {"headerId": "hdr-1"}},
                    {"createFootnote": {"footnoteId": "ft-1"}},
                ]
            }
        )

        success, msg, meta = await manager.execute_batch_operations(
            "doc-123",
            [
                {"type": "create_header_footer", "section_type": "header"},
                {"type": "create_footnote", "end_of_segment": True},
            ],
        )

        assert success
        assert meta["created_headers"] == [{"header_id": "hdr-1"}]
        assert meta["created_footnotes"] == [{"footnote_id": "ft-1"}]
        assert "Created headers: hdr-1" in msg
        assert "Created footnotes: ft-1" in msg
