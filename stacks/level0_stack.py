from aws_cdk import Duration, RemovalPolicy, Stack, Size
from aws_cdk.aws_ec2 import Vpc, SubnetSelection, SubnetType
from aws_cdk.aws_iam import Effect, PolicyStatement
from aws_cdk.aws_lambda import (
    Architecture,
    DockerImageCode,
    DockerImageFunction,
)
from aws_cdk.aws_lambda_event_sources import SqsEventSource
from aws_cdk.aws_s3 import Bucket
from aws_cdk.aws_s3_notifications import SqsDestination
from aws_cdk.aws_sqs import DeadLetterQueue, Queue
from constructs import Construct


class Level0Stack(Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        level0_bucket_name: str,
        pg_host_ssm_name: str,
        pg_user_ssm_name: str,
        pg_pass_ssm_name: str,
        pg_db_ssm_name: str,
        psql_bucket_name: str,
        queue_retention_period: Duration = Duration.days(14),
        message_timeout: Duration = Duration.hours(12),
        message_attempts: int = 4,
        lambda_timeout: Duration = Duration.seconds(900),
        **kwargs
    ) -> None:
        super().__init__(scope, id, **kwargs)

        vpc = Vpc.from_lookup(
            self,
            "OdinSMRLevel0VPC",
            is_default=False,
            vpc_name="OdinVPC",
        )
        vpc_subnets = SubnetSelection(
            subnet_type=SubnetType.PRIVATE_WITH_EGRESS
        )

        level0_lambda = DockerImageFunction(
            self,
            "OdinSMRLevel0Lambda",
            code=DockerImageCode.from_image_asset(
                ".",
            ),
            vpc=vpc,
            vpc_subnets=vpc_subnets,
            timeout=lambda_timeout,
            architecture=Architecture.X86_64,
            ephemeral_storage_size=Size.mebibytes(512),
            memory_size=1024,
            environment={
                "ODIN_PG_HOST_SSM_NAME": pg_host_ssm_name,
                "ODIN_PG_USER_SSM_NAME": pg_user_ssm_name,
                "ODIN_PG_PASS_SSM_NAME": pg_pass_ssm_name,
                "ODIN_PG_DB_SSM_NAME": pg_db_ssm_name,
                "ODIN_PSQL_BUCKET_NAME": psql_bucket_name,
            },
        )

        for ssm_name in (
            pg_host_ssm_name,
            pg_user_ssm_name,
            pg_pass_ssm_name,
            pg_db_ssm_name,
        ):
            level0_lambda.add_to_role_policy(PolicyStatement(
                effect=Effect.ALLOW,
                actions=["ssm:GetParameter"],
                resources=[f"arn:aws:ssm:*:*:parameter{ssm_name}"]
            ))

        queue_name = "ProcessLevel0Queue"
        event_queue = Queue(
            self,
            queue_name,
            queue_name=queue_name,
            visibility_timeout=message_timeout,
            removal_policy=RemovalPolicy.RETAIN,
            dead_letter_queue=DeadLetterQueue(
                max_receive_count=message_attempts,
                queue=Queue(
                    self,
                    "Failed" + queue_name,
                    queue_name="Failed" + queue_name,
                    retention_period=queue_retention_period,
                )
            )
        )

        level0_bucket = Bucket.from_bucket_name(
            self,
            "Level0Bucket",
            level0_bucket_name,
        )

        level0_bucket.add_object_created_notification(
            SqsDestination(event_queue),
        )

        level0_lambda.add_event_source(SqsEventSource(
            event_queue,
            batch_size=1,
        ))

        level0_bucket.grant_read(level0_lambda)

        psql_bucket = Bucket.from_bucket_name(
            self,
            "Level0PsqlBucket",
            psql_bucket_name,
        )

        psql_bucket.grant_read(level0_lambda)
