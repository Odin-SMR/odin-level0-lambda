from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

import boto3


BUCKET_NAME = "odin-pdc-l0"
QUEUE_NAME = "ProcessLevel0Queue"
FILE_TYPES = ("ac2", "ac1", "att", "shk", "fba")
PREFIX_RE = re.compile(r"^[0-9a-fA-F]{3}$")


def build_s3_event_message(bucket: str, key: str) -> dict[str, Any]:
    """Build a minimal S3 event structure as expected by activate_l0_handler.

    The Lambda only reads bucket name and object key from the first record.
    """

    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key},
                }
            }
        ]
    }


def send_objects_for_prefix(stw_prefix: str, profile: str | None = None) -> int:
    """List matching S3 objects and send one SQS message per object.

    Returns the number of messages sent.
    """

    if profile is not None:
        session: Any = boto3.Session(profile_name=profile)
    else:
        session = boto3.Session()

    s3_client: Any = session.client("s3")
    sqs_client: Any = session.client("sqs")

    queue_url = sqs_client.get_queue_url(QueueName=QUEUE_NAME)["QueueUrl"]

    paginator = s3_client.get_paginator("list_objects_v2")

    sent_count = 0

    for file_type in FILE_TYPES:
        prefix = f"{file_type}/{stw_prefix}"
        page_iterator = paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix)

        for page in page_iterator:
            contents = page.get("Contents")
            if not contents:
                continue

            for obj in contents:
                key = obj["Key"]
                message_body = json.dumps(build_s3_event_message(BUCKET_NAME, key))

                sqs_client.send_message(QueueUrl=queue_url, MessageBody=message_body)
                sent_count += 1

    return sent_count


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Send S3 object notifications for a given STW prefix "
            "to the ProcessLevel0Queue."
        )
    )
    parser.add_argument(
        "stw_prefix",
        help="Three-digit hex prefix (e.g. 001, 39a)",
    )
    parser.add_argument(
        "--profile",
        help=(
            "AWS profile name to use (defaults to standard "
            "credential resolution if omitted)"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    args = parse_args(argv)

    stw_prefix = args.stw_prefix.strip()
    if not PREFIX_RE.fullmatch(stw_prefix):
        print(
            "Error: stw_prefix must be a three-digit hex value, e.g. 001 or 39a",
            file=sys.stderr,
        )
        return 1

    try:
        count = send_objects_for_prefix(stw_prefix, profile=args.profile)
    except Exception as exc:  # pragma: no cover - simple CLI failure path
        print(f"Error sending messages: {exc}", file=sys.stderr)
        return 1

    print(
        f"Sent {count} message(s) for STW prefix {stw_prefix} "
        f"to SQS queue {QUEUE_NAME} in bucket {BUCKET_NAME}",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
