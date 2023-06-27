import json
import os
import stat
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import boto3

from .import_level0 import import_file


BotoClient = Any
S3Client = BotoClient
SSMClient = BotoClient
Event = dict[str, Any]
Context = Any


class InvalidMessage(Exception):
    pass


def get_env_or_raise(variable_name: str) -> str:
    if (var := os.environ.get(variable_name)) is None:
        raise EnvironmentError(
            f"{variable_name} is a required environment variable"
        )
    return var


def parse_event_message(event: Event) -> tuple[str, str]:
    try:
        message: dict[str, Any] = json.loads(event["Records"][0]["body"])
        bucket = message["Records"][0]["s3"]["bucket"]["name"]
        key = message["Records"][0]["s3"]["object"]["key"]
    except (KeyError, TypeError):
        raise InvalidMessage
    return bucket, key


def download_file(
    s3_client: S3Client,
    bucket_name: str,
    path_name: str,
    file_name: str,
) -> Path:
    file_path = Path(path_name) / file_name
    file_path.parent.mkdir(parents=True, exist_ok=True)
    s3_client.download_file(
        bucket_name,
        file_name,
        str(file_path),
    )
    return file_path


def handler(event: Event, context: Context) -> None:

    pg_host_ssm_name = get_env_or_raise("ODIN_PG_HOST_SSM_NAME")
    pg_user_ssm_name = get_env_or_raise("ODIN_PG_USER_SSM_NAME")
    pg_pass_ssm_name = get_env_or_raise("ODIN_PG_PASS_SSM_NAME")
    pg_db_ssm_name = get_env_or_raise("ODIN_PG_DB_SSM_NAME")
    psql_bucket = get_env_or_raise("ODIN_PSQL_BUCKET_NAME")

    bucket, object_path = parse_event_message(event)

    with TemporaryDirectory(
        "psql",
        "/tmp",
    ) as psql_dir, TemporaryDirectory(
        "level0",
        "/tmp/",
    ) as data_dir:
        s3_client = boto3.client('s3')

        # Setup SSL for Postgres
        pg_cert_path = download_file(
            s3_client,
            psql_bucket,
            psql_dir,
            "/postgresql.crt",
        )
        root_cert_path = download_file(
            s3_client,
            psql_bucket,
            psql_dir,
            "/root.crt",
        )
        pg_key_path = download_file(
            s3_client,
            psql_bucket,
            psql_dir,
            "/postgresql.key",
        )
        os.chmod(pg_key_path, stat.S_IWUSR | stat.S_IRUSR | stat.S_IRGRP)
        os.environ["PGSSLCERT"] = str(pg_cert_path)
        os.environ["PGSSLROOTCERT"] = str(root_cert_path)
        os.environ["PGSSLKEY"] = str(pg_key_path)

        ssm_client: SSMClient = boto3.client("ssm")
        db_host = ssm_client.get_parameter(
            Name=pg_host_ssm_name,
            WithDecryption=True,
        )["Parameter"]["Value"]
        db_user = ssm_client.get_parameter(
            Name=pg_user_ssm_name,
            WithDecryption=True,
        )["Parameter"]["Value"]
        db_pass = ssm_client.get_parameter(
            Name=pg_pass_ssm_name,
            WithDecryption=True,
        )["Parameter"]["Value"]
        db_name = ssm_client.get_parameter(
            Name=pg_db_ssm_name,
            WithDecryption=True,
        )["Parameter"]["Value"]

        # Import Level 0 file
        file_path = download_file(s3_client, bucket, data_dir, object_path)

        import_file(
            str(file_path),
            host=db_host,
            user=db_user,
            secret=db_pass,
            db_name=db_name,
        )
