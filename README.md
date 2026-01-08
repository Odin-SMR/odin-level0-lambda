Odin SMR Level 0 Workflow
=========================

This repository contains the AWS CDK application and Lambda code that implement
the Odin SMR Level 0 (L0) processing workflow. It provisions the S3/SQS/Step
Functions/Lambda pipeline and packages the Python code and its dependencies for
deployment.

This document explains how to develop on top of the existing code and how the
GitHub Actions CI/CD workflows relate to that development.


Overview
--------

High‑level architecture (see [app.py](app.py) and
[stacks/level0_stack.py](stacks/level0_stack.py)):

- CDK app defines a single stack `Level0Stack` that:
	- Looks up an existing VPC `OdinVPC`.
	- Wires an S3 bucket containing L0 files to an SQS queue.
	- Uses the SQS queue to trigger a Lambda that activates the L0 processing
		Step Functions state machine.
	- Runs an "import L0" Lambda that reads the original file and writes
		pre‑processed/PSQL data.
	- Runs a notifier Lambda that tells the Level 1 processor when relevant
		Level 0 data is available.

Relevant code locations:

- Infrastructure: [stacks/level0_stack.py](stacks/level0_stack.py)
- CDK app entry point: [app.py](app.py)
- L0 import Lambda code and dependencies:
	- Code: [level0/import_l0/](level0/import_l0)
	- Tests: [tests/level0/handler/test_import_level0.py](tests/level0/handler/test_import_level0.py)
- Activate L0 Lambda: [level0/activate_l0/](level0/activate_l0)
- Notify L1 Lambda: [level0/notify_l1/](level0/notify_l1)

Python packaging and dependency management is handled via `uv` and
[pyproject.toml](pyproject.toml).


Local Development
-----------------

### Prerequisites

- Python 3.13 (the version is defined in `.python-version`).
- `uv` package manager (matches the CI configuration).
- Node.js 22 and `aws-cdk` CLI (for local synth/deploy):
	- `npm install -g aws-cdk`
- AWS credentials with permission to synth/deploy the stack if you want to
	run CDK commands locally.


Project Installation
--------------------

Install all dependencies (including dev tools and Lambda extras) using `uv`:

```bash
uv sync --locked --all-groups
```

This mirrors what the CI workflow does in the `tests` job.

After syncing, you can run commands through `uv` to ensure they use the same
environment as the CI/CD pipelines, for example:

```bash
uv run --no-sync pytest
```


Running Checks and Tests Locally
--------------------------------

The CI workflow [.github/workflows/ci.yml](.github/workflows/ci.yml) runs a
series of checks on every push. You should run the same commands locally before
opening a pull request:

```bash
# Ruff lint
uv run --no-sync ruff check .

# Black formatting check
uv run --no-sync black --check .

# MyPy type checking
uv run --no-sync mypy .

# Unit tests
uv run --no-sync pytest
```

Keeping your changes green under these commands will keep CI green as well.


CDK: Synthesizing and Deploying
-------------------------------

The CDK app is defined in [app.py](app.py) and deploys `Level0Stack` from
[stacks/level0_stack.py](stacks/level0_stack.py).

Typical local workflow:

```bash
# Synthesize the CloudFormation templates
uv run --no-sync cdk synth

# Deploy the stack (to your currently configured AWS account)
uv run --no-sync cdk deploy --all --require-approval never
```

Make sure you have appropriate AWS credentials configured in your shell (for
example using `aws configure` or `AWS_PROFILE`) before running these commands.

In CI/CD, CDK uses the role `arn:aws:iam::991049544436:role/OdinGithubRole` as
configured in the workflows.


Lambda Dependencies and Packaging
---------------------------------

The import L0 Lambda uses a dedicated dependency group in
[pyproject.toml](pyproject.toml):

- Group `import-l0` contains runtime dependencies (e.g. `numpy`,
	`psycopg2-binary`, `pygresql`).

For deployment, the GitHub Actions workflows perform two key steps:

1. Generate a `requirements.txt` specific to the import L0 Lambda:

	 ```bash
	 uv export --locked --only-group import-l0 --no-editable \
		 -o level0/import_l0/requirements.txt
	 ```

2. Install those dependencies into the Lambda vendor directory that gets
	 packaged with the function code:

	 ```bash
	 uv pip install \
		 --no-installer-metadata \
		 --no-compile-bytecode \
		 --python-platform x86_64-manylinux2014 \
		 --python 3.13 \
		 --target level0/import_l0/vendor \
		 -r level0/import_l0/requirements.txt
	 ```

If you need additional runtime dependencies for the import L0 Lambda:

1. Add them to the `import-l0` dependency group in [pyproject.toml](pyproject.toml).
2. Re‑run the two commands above locally if you want to test packaging, or rely
	 on the CI/CD workflows to do this as part of synth/deploy.


GitHub Actions CI
-----------------

The workflow [.github/workflows/ci.yml](.github/workflows/ci.yml) runs on every
push and contains two jobs:

1. `tests` job (no AWS credentials required):
	 - Checks out the repository.
	 - Sets up Python (version from `.python-version`).
	 - Installs `uv`.
	 - Runs `uv sync --locked --all-groups`.
	 - Runs `ruff check`, `black --check`, `mypy`, and `pytest` via `uv run`.

	 This job ensures code style, types, and tests all pass.

2. `cdk-synth` job (uses AWS credentials via `OdinGithubRole`):
	 - Checks out the repository.
	 - Sets up Node 22 and installs `aws-cdk` globally.
	 - Configures AWS credentials using the configured IAM role.
	 - Sets up Python and `uv`.
	 - Generates import L0 Lambda requirements and installs them into
		 `level0/import_l0/vendor`.
	 - Runs `uv sync --locked --no-dev` to install only runtime dependencies.
	 - Runs `uv run --no-sync cdk synth`.

	 This job verifies that the infrastructure code and packaging are valid and
	 that CDK can synthesize the stack.


GitHub Actions CD (Deployment)
------------------------------

The workflow [.github/workflows/cd.yml](.github/workflows/cd.yml) is responsible
for deploying the stack to AWS.

Triggers:

- `release` with type `released` (i.e. when you publish a GitHub Release).
- `workflow_dispatch` (manual run from the GitHub UI).

Steps (in the `deploy` job):

- Same environment setup as `cdk-synth` (Node 22, `aws-cdk`, AWS credentials,
	Python, `uv`).
- Generates import L0 Lambda requirements and installs them into
	`level0/import_l0/vendor`.
- Runs `uv sync --locked --no-dev` to install runtime dependencies for CDK.
- Runs `uv run --no-sync cdk deploy --all --require-approval never` to deploy
	all stacks.

Typical deployment flow:

1. Merge your feature branch into the main branch after CI passes.
2. Create and publish a GitHub Release for the new version.
3. The `Odin SMR L0 processing CD` workflow runs and deploys the latest
	 infrastructure and Lambda code.


Making Code Changes Safely
--------------------------

When developing new features or changing existing behavior, a typical workflow
is:

1. Create a feature branch from `main`.
2. Make your code changes:
	 - Lambda logic in `level0/import_l0`, `level0/activate_l0`, or
		 `level0/notify_l1` as appropriate.
	 - Infrastructure or state machine logic in
		 [stacks/level0_stack.py](stacks/level0_stack.py).
3. Update or add tests in `tests/` (for example
	 [tests/level0/handler/test_import_level0.py](tests/level0/handler/test_import_level0.py)).
4. Run the local checks and tests listed above.
5. Optionally run `uv run --no-sync cdk synth` locally to confirm the stack
	 still synthesizes.
6. Open a pull request; CI will re‑run the same checks.
7. After review and merge, cut a GitHub Release to trigger deployment.


Extending the Workflow
----------------------

Some common extension points and where to look in the code:

- **Adding or changing import logic**
	- Modify or extend the import Lambda code under
		[level0/import_l0/](level0/import_l0).
	- Add tests under `tests/level0` (for example, the existing
		`stw_correction` tests).

- **Changing how files are routed or retried**
	- The Step Functions definition and routing logic (e.g. based on the
		imported file type) live in
		[stacks/level0_stack.py](stacks/level0_stack.py), in the
		`Level0Stack` constructor.

- **Adding new Lambdas or state machine branches**
	- Add new Lambda definitions, IAM policies, and Step Functions tasks in
		[stacks/level0_stack.py](stacks/level0_stack.py).
	- Place the corresponding Lambda code in an appropriate
		`level0/<new_lambda>/` directory and wire it up in the stack.

Whenever you extend the workflow, make sure the CI checks stay green and that
`cdk synth` still succeeds before you attempt a deployment.


Where to Ask for Help
---------------------

If anything in this document is unclear or you encounter issues when running
the commands locally, consider:

- Checking the latest versions of the GitHub Actions workflows under
	`.github/workflows/` to see the exact CI/CD behavior.
- Looking at recent pull requests and commit history to understand current
	conventions.

