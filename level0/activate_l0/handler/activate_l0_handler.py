import hashlib
import json
import time
from typing import Any

import boto3


Event = dict[str, Any]
Context = Any

STATE_MACHINE_NAME = "OdinSMRImportLevel0StateMachine"


class StateMachineError(Exception):
    pass


class InvalidMessage(Exception):
    pass


def parse_event_message(event: Event) -> tuple[str, str]:
    try:
        message: dict[str, Any] = json.loads(event["Records"][0]["body"])
        bucket = message["Records"][0]["s3"]["bucket"]["name"]
        key = message["Records"][0]["s3"]["object"]["key"]
    except (KeyError, TypeError):
        raise InvalidMessage
    return bucket, key


def find_arn() -> str | None:
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

    state_machine_arn = find_arn()

    bucket, object_path = parse_event_message(event)

    sfn = boto3.client("stepfunctions")
    if state_machine_arn is not None:
        sfn.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps({"bucket": bucket, "key": object_path}),
            name=f"{object_path.replace('/', '-')}-{create_short_hash()}",
        )

        return {
            "StatusCode": 200,
        }
    else:
        return {
            "StatusCode": 500,
        }
