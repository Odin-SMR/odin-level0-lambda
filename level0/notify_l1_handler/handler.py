import hashlib
import json
import time
from typing import Any

import boto3


Event = dict[str, str]
Context = Any

STATE_MACHINE_NAME = "OdinSMRLevel1StateMachine"


class StateMachineError(Exception):
    pass


def find_arn() -> str:
    client = boto3.client("stepfunctions")
    results = client.list_state_machines()
    state_machine_arn: str | None = None
    for i in results["stateMachines"]:
        if i["name"] == STATE_MACHINE_NAME:
            state_machine_arn = i["stateMachineArn"]
            break
    if state_machine_arn is None:
        raise StateMachineError(
            f"no matching state machine {STATE_MACHINE_NAME} found"
        )
    return state_machine_arn


def create_short_hash() -> str:
    input_data = str(time.time()).encode("utf-8")
    hash_object = hashlib.sha256(input_data)
    short_hash = hash_object.hexdigest()[:8]
    return short_hash


def handler(event: Event, context: Context) -> dict[str, int]:

    state_machine_arn = find_arn()
    if state_machine_arn is None:
        raise StateMachineError(
            f"no matching state machine {STATE_MACHINE_NAME} found"
        )

    sfn = boto3.client("stepfunctions")

    sfn.start_execution(
        stateMachineArn=state_machine_arn,
        input=json.dumps(event),
        name=f"{event['name']}-{create_short_hash()}",
    )

    return {
        "StatusCode": 200,
    }
