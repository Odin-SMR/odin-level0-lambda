from typing import Any

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from aws_cdk.aws_ec2 import SubnetSelection, SubnetType, Vpc
from aws_cdk.aws_iam import Effect, PolicyStatement
from aws_cdk.aws_lambda import Architecture, Code, Function, InlineCode, Runtime
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
        ssm_root: str,
        psql_bucket_name: str,
        queue_retention_period: Duration = Duration.days(14),
        message_timeout: Duration = Duration.hours(12),
        message_attempts: int = 4,
        lambda_timeout: Duration = Duration.seconds(900),
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # Set up VPC
        vpc = Vpc.from_lookup(
            self,
            "OdinSMRLevel0VPC",
            is_default=False,
            vpc_name="OdinVPC",
        )
        vpc_subnets = SubnetSelection(subnet_type=SubnetType.PRIVATE_WITH_EGRESS)

        # Set up Lambda functions
        import_level0_lambda = Function(
            self,
            "OdinSMRImportLevel0Lambda",
            function_name="OdinSMRImportLevel0Lambda",
            handler="import_l0_handler.import_l0_handler",
            code=Code.from_asset("./level0/import_l0"),
            timeout=lambda_timeout,
            architecture=Architecture.X86_64,
            runtime=Runtime.PYTHON_3_13,
            vpc=vpc,
            vpc_subnets=vpc_subnets,
            memory_size=1024,
            environment={
                "ODIN_PG_HOST_SSM_NAME": f"{ssm_root}/host",
                "ODIN_PG_USER_SSM_NAME": f"{ssm_root}/user",
                "ODIN_PG_PASS_SSM_NAME": f"{ssm_root}/password",
                "ODIN_PG_DB_SSM_NAME": f"{ssm_root}/db",
                "ODIN_PSQL_BUCKET_NAME": psql_bucket_name,
                "PYTHONPATH": "/var/task/vendor",
            },
        )

        import_level0_lambda.add_to_role_policy(
            PolicyStatement(
                effect=Effect.ALLOW,
                actions=["ssm:GetParameter"],
                resources=[f"arn:aws:ssm:*:*:parameter{ssm_root}/*"],
            )
        )

        activate_level0_lambda = Function(
            self,
            "OdinSMRLevel0Lambda",
            function_name="OdinSMRLevel0Lambda",
            code=InlineCode.from_asset("./level0/activate_l0"),
            handler="handler.activate_l0_handler.activate_l0_handler",
            timeout=lambda_timeout,
            architecture=Architecture.X86_64,
            runtime=Runtime.PYTHON_3_13,
        )

        activate_level0_lambda.add_to_role_policy(
            PolicyStatement(
                actions=[
                    "states:ListStateMachines",
                    "states:StartExecution",
                ],
                resources=["*"],
            ),
        )

        notify_level1_lambda = Function(
            self,
            "OdinSMRLevel1Notifier",
            function_name="OdinSMRLevel1Notifier",
            code=InlineCode.from_asset("./level0/notify_l1"),
            handler="handler.notify_l1_handler.notify_l1_handler",
            timeout=lambda_timeout,
            architecture=Architecture.X86_64,
            runtime=Runtime.PYTHON_3_13,
        )

        notify_level1_lambda.add_to_role_policy(
            PolicyStatement(
                actions=[
                    "states:ListStateMachines",
                    "states:StartExecution",
                ],
                resources=["*"],
            ),
        )

        # Set up queue of S3 notifications
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
                ),
            ),
        )

        level0_bucket = Bucket.from_bucket_name(
            self,
            "Level0Bucket",
            level0_bucket_name,
        )

        level0_bucket.add_object_created_notification(
            SqsDestination(event_queue),
        )

        # Set up tasks
        import_level0_task = tasks.LambdaInvoke(
            self,
            "OdinSMRImportLevel0Task",
            lambda_function=import_level0_lambda,
            payload=sfn.TaskInput.from_object(
                {
                    "bucket": sfn.JsonPath.string_at("$.bucket"),
                    "key": sfn.JsonPath.string_at("$.key"),
                },
            ),
            result_path="$.ImportLevel0",
        )
        import_level0_task.add_retry(
            errors=["States.ALL"],
            max_attempts=42,
            backoff_rate=2,
            interval=Duration.minutes(6),
            jitter_strategy=sfn.JitterType.FULL,
            max_delay=Duration.minutes(60),
        )

        notify_level1_task = tasks.LambdaInvoke(
            self,
            "OdinSMRNotifyLevel1Task",
            lambda_function=notify_level1_lambda,
            payload=sfn.TaskInput.from_object(
                {
                    "name": sfn.JsonPath.string_at("$.key"),
                    "type": sfn.JsonPath.string_at(
                        "$.ImportLevel0.Payload.type"
                    ),  # noqa: E501
                },
            ),
            result_path="$.NotifyLevel1",
        )
        notify_level1_task.add_retry(
            errors=["States.ALL"],
            max_attempts=42,
            backoff_rate=2,
            interval=Duration.minutes(6),
            jitter_strategy=sfn.JitterType.FULL,
            max_delay=Duration.minutes(60),
        )

        # Set up flow
        import_level0_fail_state = sfn.Fail(
            self,
            "OdinSMRImportLevel0Fail",
            comment="Somthing went wrong when importing Level 0 file",
        )
        import_level0_success_state = sfn.Succeed(
            self,
            "OdinSMRImportLevel0Success",
        )
        import_level0_skip_file_state = sfn.Succeed(
            self,
            "OdinSMRImportLevel0SkipFile",
            comment="Execution OK but unknown file type, mode or similar",
        )
        check_import_status_state = sfn.Choice(
            self,
            "OdinSMRCheckImportStatus",
        )
        import_level0_task.next(check_import_status_state)
        check_import_status_state.when(
            sfn.Condition.boolean_equals(
                "$.ImportLevel0.Payload.imported",
                False,
            ),
            import_level0_skip_file_state,
        )
        check_import_status_state.when(
            sfn.Condition.or_(
                sfn.Condition.string_equals(
                    "$.ImportLevel0.Payload.type",
                    "ac1",
                ),
                sfn.Condition.string_equals(
                    "$.ImportLevel0.Payload.type",
                    "ac2",
                ),
            ),
            notify_level1_task,
        )
        check_import_status_state.when(
            sfn.Condition.or_(
                sfn.Condition.string_equals(
                    "$.ImportLevel0.Payload.type",
                    "fba",
                ),
                sfn.Condition.string_equals(
                    "$.ImportLevel0.Payload.type",
                    "att",
                ),
                sfn.Condition.string_equals(
                    "$.ImportLevel0.Payload.type",
                    "shk",
                ),
            ),
            import_level0_success_state,
        )
        check_import_status_state.otherwise(import_level0_fail_state)

        notify_level1_fail_state = sfn.Fail(
            self,
            "OdinSMRImportNotifyLevel1Fail",
            comment="Somthing went wrong when notifying Level 1 processor",
        )
        notify_level1_success_state = sfn.Succeed(
            self,
            "OdinSMRImportNotifyLevel1Success",
        )
        check_notify_status_state = sfn.Choice(
            self,
            "OdinSMRCheckNotifyLevel1Status",
        )
        notify_level1_task.next(check_notify_status_state)
        check_notify_status_state.when(
            sfn.Condition.number_equals(
                "$.NotifyLevel1.Payload.StatusCode",
                200,
            ),
            notify_level1_success_state,
        )
        check_notify_status_state.otherwise(notify_level1_fail_state)

        random_wait_seconds = sfn.Pass(
            self,
            "OdinSMRGenerateWaitSeconds",
            parameters={
                # put it where your Wait state's seconds_path expects it
                "waitSeconds.$": "States.MathRandom(0, 3600)"
            },
            result_path="$.wait",  # store under $.wait.waitSeconds
        )

        wait_state = sfn.Wait(
            self,
            "OdinSMRLevel0Wait",
            time=sfn.WaitTime.seconds_path("$.wait.waitSeconds"),
        )

        start = random_wait_seconds.next(wait_state).next(import_level0_task)

        sfn.StateMachine(
            self,
            "OdinSMRImportLevel0StateMachine",
            definition=start,
            state_machine_name="OdinSMRImportLevel0StateMachine",
        )

        # Set up event source
        activate_level0_lambda.add_event_source(
            SqsEventSource(
                event_queue,
                batch_size=1,
            )
        )

        # Set up additional permissions
        level0_bucket.grant_read(import_level0_lambda)

        psql_bucket = Bucket.from_bucket_name(
            self,
            "Level0PsqlBucket",
            psql_bucket_name,
        )

        psql_bucket.grant_read(import_level0_lambda)
