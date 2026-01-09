"""Tests for activate_l0_handler Lambda function.

These tests validate proper SQS message acknowledgment behavior:
- Successful processing returns normally (message acked)
- Invalid messages are caught and acked to prevent infinite retries
- Transient errors propagate for retry
"""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from level0.activate_l0.handler.activate_l0_handler import (
    InvalidMessage,
    StateMachineError,
    activate_l0_handler,
    create_short_hash,
    find_arn,
    parse_event_message,
)


def create_sqs_event(bucket: str, key: str) -> dict[str, Any]:
    """Create a valid SQS event with S3 notification."""
    s3_event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key},
                }
            }
        ]
    }
    return {
        "Records": [
            {
                "body": json.dumps(s3_event),
            }
        ]
    }


class TestParseEventMessage:
    """Test message parsing."""

    def test_parse_valid_message(self) -> None:
        """Valid message should be parsed correctly."""
        event = create_sqs_event("test-bucket", "test-key")
        bucket, key = parse_event_message(event)
        assert bucket == "test-bucket"
        assert key == "test-key"

    def test_parse_invalid_json(self) -> None:
        """Invalid JSON should raise InvalidMessage."""
        event = {"Records": [{"body": "not-json"}]}
        with pytest.raises(InvalidMessage):
            parse_event_message(event)

    def test_parse_missing_records(self) -> None:
        """Missing Records field should raise InvalidMessage."""
        event: dict[str, Any] = {}
        with pytest.raises(InvalidMessage):
            parse_event_message(event)

    def test_parse_missing_s3_fields(self) -> None:
        """Missing S3 fields should raise InvalidMessage."""
        event = {"Records": [{"body": json.dumps({"Records": [{}]})}]}
        with pytest.raises(InvalidMessage):
            parse_event_message(event)


class TestFindArn:
    """Test state machine ARN lookup."""

    @patch("level0.activate_l0.handler.activate_l0_handler.boto3")
    def test_find_arn_success(self, mock_boto3: MagicMock) -> None:
        """Should find and return state machine ARN."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.list_state_machines.return_value = {
            "stateMachines": [
                {
                    "name": "OdinSMRImportLevel0StateMachine",
                    "stateMachineArn": "arn:aws:states:region:account:stateMachine:test",
                }
            ]
        }

        arn = find_arn()
        assert arn == "arn:aws:states:region:account:stateMachine:test"

    @patch("level0.activate_l0.handler.activate_l0_handler.boto3")
    def test_find_arn_not_found(self, mock_boto3: MagicMock) -> None:
        """Should raise StateMachineError when not found."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.list_state_machines.return_value = {"stateMachines": []}

        with pytest.raises(
            StateMachineError,
            match="no matching state machine OdinSMRImportLevel0StateMachine found",
        ):
            find_arn()


class TestCreateShortHash:
    """Test hash generation."""

    def test_create_short_hash(self) -> None:
        """Should create an 8-character hash."""
        hash1 = create_short_hash()
        assert len(hash1) == 8
        assert hash1.isalnum()


class TestActivateL0Handler:
    """Test the main handler function and message acknowledgment behavior."""

    @patch("level0.activate_l0.handler.activate_l0_handler.boto3")
    def test_successful_processing(self, mock_boto3: MagicMock) -> None:
        """Successful processing should return 200 (message acked)."""
        # Mock Step Functions client
        mock_sfn_client = MagicMock()
        mock_boto3.client.side_effect = [
            mock_sfn_client,  # First call for find_arn
            mock_sfn_client,  # Second call for start_execution
        ]
        mock_sfn_client.list_state_machines.return_value = {
            "stateMachines": [
                {
                    "name": "OdinSMRImportLevel0StateMachine",
                    "stateMachineArn": "arn:aws:states:region:account:stateMachine:test",
                }
            ]
        }
        mock_sfn_client.start_execution.return_value = {
            "executionArn": "arn:aws:states:region:account:execution:test"
        }

        event = create_sqs_event("test-bucket", "ac1/test-file.ac1")
        context = MagicMock()

        result = activate_l0_handler(event, context)

        assert result == {"StatusCode": 200}
        mock_sfn_client.start_execution.assert_called_once()

    @patch("level0.activate_l0.handler.activate_l0_handler.boto3")
    def test_invalid_message_acked(self, mock_boto3: MagicMock) -> None:
        """Invalid message should return 200 to ack (prevent infinite retries)."""
        # Invalid event that will trigger InvalidMessage
        event = {"Records": [{"body": "invalid-json"}]}
        context = MagicMock()

        result = activate_l0_handler(event, context)

        # Should return success to ack the invalid message
        assert result == {"StatusCode": 200}
        # Should not call Step Functions
        mock_boto3.client.assert_not_called()

    @patch("level0.activate_l0.handler.activate_l0_handler.boto3")
    def test_state_machine_error_propagates(self, mock_boto3: MagicMock) -> None:
        """StateMachineError should propagate (message nacked for retry)."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.list_state_machines.return_value = {"stateMachines": []}

        event = create_sqs_event("test-bucket", "test-key")
        context = MagicMock()

        # Should raise exception so Lambda nacks the message
        with pytest.raises(StateMachineError):
            activate_l0_handler(event, context)

    @patch("level0.activate_l0.handler.activate_l0_handler.boto3")
    def test_unexpected_error_propagates(self, mock_boto3: MagicMock) -> None:
        """Unexpected errors should propagate (message nacked for retry)."""
        mock_sfn_client = MagicMock()
        mock_boto3.client.side_effect = [
            mock_sfn_client,  # First call for find_arn
            mock_sfn_client,  # Second call for start_execution
        ]
        mock_sfn_client.list_state_machines.return_value = {
            "stateMachines": [
                {
                    "name": "OdinSMRImportLevel0StateMachine",
                    "stateMachineArn": "arn:aws:states:region:account:stateMachine:test",
                }
            ]
        }
        # Simulate an API error
        mock_sfn_client.start_execution.side_effect = Exception("API error")

        event = create_sqs_event("test-bucket", "test-key")
        context = MagicMock()

        # Should raise exception so Lambda nacks the message
        with pytest.raises(Exception, match="API error"):
            activate_l0_handler(event, context)
