#!/usr/bin/env python3
"""CDK app entry point. See docs/aws_deployment.md for the deploy sequence."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import aws_cdk as cdk

from api_stack import ApiStack
from data_stack import DataStack

INFRA_DIR = Path(__file__).resolve().parent
REPO_ROOT = INFRA_DIR.parent
LAMBDA_BUILD_DIR = INFRA_DIR / "build" / "lambda_package"
LAMBDA_REQUIREMENTS = INFRA_DIR / "lambda_requirements.txt"


def build_lambda_asset() -> str:
    """Pre-build the API Lambda's deployment package without Docker: pip-install
    the runtime-only dependencies (infra/lambda_requirements.txt -- not the repo's
    top-level requirements.txt, which also carries pytest/httpx/uvicorn that the
    Lambda never needs) for the Lambda platform into a local directory, then copy
    the app source in. CDK's usual Docker-based bundling isn't used here because
    Docker isn't available in this environment; see docs/aws_deployment.md."""
    needs_build = not LAMBDA_BUILD_DIR.exists() or (
        LAMBDA_REQUIREMENTS.stat().st_mtime > LAMBDA_BUILD_DIR.stat().st_mtime
    )

    if not needs_build:
        return str(LAMBDA_BUILD_DIR)

    if LAMBDA_BUILD_DIR.exists():
        shutil.rmtree(LAMBDA_BUILD_DIR)
    LAMBDA_BUILD_DIR.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--platform",
            "manylinux2014_x86_64",
            "--implementation",
            "cp",
            "--python-version",
            "3.13",
            "--only-binary=:all:",
            "--target",
            str(LAMBDA_BUILD_DIR),
            "-r",
            str(LAMBDA_REQUIREMENTS),
        ],
        check=True,
    )

    shutil.copytree(REPO_ROOT / "app", LAMBDA_BUILD_DIR / "app")
    shutil.copy2(REPO_ROOT / "lambda_handler.py", LAMBDA_BUILD_DIR / "lambda_handler.py")
    shutil.copytree(REPO_ROOT / "data" / "rules", LAMBDA_BUILD_DIR / "data" / "rules")

    return str(LAMBDA_BUILD_DIR)


app = cdk.App()

env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"),
)

data_stack = DataStack(app, "VendorGateDataStack", env=env)

ApiStack(
    app,
    "VendorGateApiStack",
    decisions_table=data_stack.decisions_table,
    reviews_table=data_stack.reviews_table,
    decision_history_table=data_stack.decision_history_table,
    review_history_table=data_stack.review_history_table,
    audit_bucket=data_stack.audit_bucket,
    user_pool=data_stack.user_pool,
    user_pool_client=data_stack.user_pool_client,
    lambda_asset_path=build_lambda_asset(),
    env=env,
)

app.synth()
