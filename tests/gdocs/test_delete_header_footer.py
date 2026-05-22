"""
Tests for the delete_header and delete_footer operations in batch_update_doc.

Covers helper construction, validate_operation, batch manager integration.
"""

from unittest.mock import Mock

import pytest

from gdocs.docs_helpers import (
    create_delete_footer_request,
    create_delete_header_request,
    validate_operation,
)


class TestCreateDeleteHeaderRequest:
    def test_basic(self):
        result = create_delete_header_request("hdr-123")
        assert result == {"deleteHeader": {"headerId": "hdr-123"}}

    def test_with_tab_id(self):
        result = create_delete_header_request("hdr-123", tab_id="t.abc")
        assert result == {
            "deleteHeader": {
                "headerId": "hdr-123",
                "tabsCriteria": {"tabIds": ["t.abc"]},
            }
        }


class TestCreateDeleteFooterRequest:
    def test_basic(self):
        result = create_delete_footer_request("ftr-456")
        assert result == {"deleteFooter": {"footerId": "ftr-456"}}


class TestValidateOperation:
    def test_delete_header_missing_id(self):
        is_valid, msg = validate_operation({"type": "delete_header"})
        assert not is_valid
        assert "header_id" in msg

    def test_delete_footer_missing_id(self):
        is_valid, msg = validate_operation({"type": "delete_footer"})
        assert not is_valid
        assert "footer_id" in msg


class TestBatchManagerIntegration:
    @pytest.fixture()
    def manager(self):
        from gdocs.managers.batch_operation_manager import BatchOperationManager

        return BatchOperationManager(Mock())

    def test_build_delete_header_through_dispatch(self, manager):
        request, desc = manager._build_operation_request(
            {"type": "delete_header", "header_id": "hdr-1"},
            "delete_header",
        )
        assert request == {"deleteHeader": {"headerId": "hdr-1"}}
        assert "delete header hdr-1" in desc

    def test_build_delete_footer_through_dispatch(self, manager):
        request, desc = manager._build_operation_request(
            {"type": "delete_footer", "footer_id": "ftr-1"},
            "delete_footer",
        )
        assert request == {"deleteFooter": {"footerId": "ftr-1"}}
        assert "delete footer ftr-1" in desc
