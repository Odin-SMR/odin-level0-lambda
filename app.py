#!/usr/bin/env python3
from aws_cdk import App, Environment

from stacks.level0_stack import Level0Stack

env_EU = Environment(account="991049544436", region="eu-north-1")

app = App()

Level0Stack(
    app,
    "OdinSMRLevel0LambdaStack",
    level0_bucket_name="odin-pdc-l0",
    ssm_root="/odin/psql",
    psql_bucket_name="odin-psql",
    env=env_EU,
)

app.synth()
