import hashlib
import json
import logging
import time
from typing import Any

import boto3


Event = dict[str, Any]
Context = Any

STATE_MACHINE_NAME = "OdinSMRImportLevel0StateMachine"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class StateMachineError(Exception):
    pass


class InvalidMessage(Exception):
    pass


def parse_event_message(event: Event) -> tuple[str, str]:
    try:
        message: dict[str, Any] = json.loads(event["Records"][0]["body"])
        bucket = message["Records"][0]["s3"]["bucket"]["name"]
        key = message["Records"][0]["s3"]["object"]["key"]
    except (KeyError, TypeError, json.JSONDecodeError):
        raise InvalidMessage
    return bucket, key


def find_arn() -> str:
    client = boto3.client("stepfunctions")
    results = client.list_state_machines()
    state_machine_arn: str | None = None
    for i in results["stateMachines"]:
        if i["name"] == STATE_MACHINE_NAME:
            state_machine_arn = i["stateMachineArn"]
            break
    if state_machine_arn is None:
        raise StateMachineError(f"no matching state machine {STATE_MACHINE_NAME} found")
    return state_machine_arn


def create_short_hash() -> str:
    input_data = str(time.time()).encode("utf-8")
    hash_object = hashlib.sha256(input_data)
    short_hash = hash_object.hexdigest()[:8]
    return short_hash


def activate_l0_handler(event: Event, context: Context) -> dict[str, int]:
    """Process SQS event and start Step Functions execution.

    This function handles messages from ProcessLevel0Queue and starts
    the Level 0 import Step Functions workflow. Message acknowledgment:

    - If processing succeeds: Returns normally, message is acked (deleted from queue)
    - If InvalidMessage is raised: Catches it, logs error, returns success to ack
      the permanently malformed message and prevent infinite retries
    - If other exceptions occur: Propagates them so AWS nacks the message for retry

    Args:
        event: Lambda event containing SQS messages
        context: Lambda context

    Returns:
        dict with StatusCode 200 on success
    """
    try:
        # Parse the SQS message containing S3 event
        bucket, object_path = parse_event_message(event)
        logger.info(f"Processing S3 object: s3://{bucket}/{object_path}")

        # Find the Step Functions state machine ARN
        state_machine_arn = find_arn()
        logger.info(f"Found state machine: {state_machine_arn}")

        # Start Step Functions execution
        sfn = boto3.client("stepfunctions")
        execution_name = f"{object_path.replace('/', '-')}-{create_short_hash()}"
        sfn.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps({"bucket": bucket, "key": object_path}),
            name=execution_name,
        )

        logger.info(f"Started Step Functions execution: {execution_name}")
        return {
            "StatusCode": 200,
        }

    except InvalidMessage as e:
        # Permanent error - malformed message that won't be fixed by retrying
        # Log the error and return success to ack the message (remove from queue)
        logger.error(f"Invalid message format, acknowledging to prevent retry: {e}")
        logger.error(f"Event that caused error: {json.dumps(event)}")
        return {
            "StatusCode": 200,  # Return success to ack the message
        }

    except StateMachineError as e:
        # State machine not found - this could be a deployment issue
        # Let this propagate to nack the message for retry
        logger.error(f"State machine error: {e}")
        raise

    except Exception as e:
        # Unexpected error - let it propagate to nack for retry
        logger.error(f"Unexpected error processing message: {e}")
        raise
