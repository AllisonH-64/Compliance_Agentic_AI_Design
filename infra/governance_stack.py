import os

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_budgets as budgets,
    aws_iam as iam,
)
from constructs import Construct

GITHUB_REPO = "AllisonH-64/Compliance_Agentic_AI_Design"


class GovernanceStack(Stack):
    """Account-level governance, independent of the app itself: the IAM role
    GitHub Actions assumes via OIDC to deploy this app, and an AWS Budget with
    email alerts. Deployed once, by hand, before CI/CD can do anything --
    see docs/aws_deployment.md for the bootstrap sequence."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # A GitHub OIDC provider is a single, account-wide resource. If this
        # account has already set one up for another repo, creating a second one
        # here will fail synth/deploy with "already exists" -- swap this line for
        # iam.OpenIdConnectProvider.from_open_id_connect_provider_arn(...) against
        # the existing provider's ARN in that case.
        github_oidc_provider = iam.OpenIdConnectProvider(
            self,
            "GitHubOidcProvider",
            url="https://token.actions.githubusercontent.com",
            client_ids=["sts.amazonaws.com"],
        )

        # Trust is scoped to this exact repo, and only to pushes on main -- a
        # workflow run from a fork or a feature branch cannot assume this role.
        deploy_role = iam.Role(
            self,
            "GitHubActionsDeployRole",
            role_name="github-actions-vendor-gate-deploy",
            assumed_by=iam.OpenIdConnectPrincipal(
                github_oidc_provider,
                conditions={
                    "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
                    "StringLike": {"token.actions.githubusercontent.com:sub": f"repo:{GITHUB_REPO}:ref:refs/heads/main"},
                },
            ),
            max_session_duration=Duration.hours(1),
            description="Assumed by GitHub Actions via OIDC (no long-lived AWS keys) to deploy this app from main.",
        )

        # This role holds no service permissions of its own. `cdk bootstrap`
        # creates a fixed set of deploy/file-publishing/lookup roles that already
        # hold exactly the permissions CDK deploys need, scoped by the bootstrap
        # qualifier -- granting sts:AssumeRole on those is the standard
        # least-privilege pattern for GitHub OIDC + CDK, instead of duplicating a
        # broad hand-written service policy here.
        deploy_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=[f"arn:aws:iam::{self.account}:role/cdk-*"],
            )
        )

        CfnOutput(
            self,
            "GitHubActionsDeployRoleArn",
            value=deploy_role.role_arn,
            description="Put this in the repo's AWS_DEPLOY_ROLE_ARN GitHub Actions secret.",
        )

        alert_email = os.getenv("BUDGET_ALERT_EMAIL")
        if not alert_email:
            raise ValueError(
                "BUDGET_ALERT_EMAIL must be set before synthesizing GovernanceStack -- "
                "a budget with no working notification path isn't cost governance, "
                "it's a line item nobody reads. Example: "
                "BUDGET_ALERT_EMAIL=you@example.com cdk deploy VendorGateGovernanceStack"
            )
        monthly_limit_usd = float(os.getenv("BUDGET_MONTHLY_LIMIT_USD", "25"))

        def _notification(notification_type: str, threshold: float) -> budgets.CfnBudget.NotificationWithSubscribersProperty:
            return budgets.CfnBudget.NotificationWithSubscribersProperty(
                notification=budgets.CfnBudget.NotificationProperty(
                    notification_type=notification_type,
                    comparison_operator="GREATER_THAN",
                    threshold=threshold,
                    threshold_type="PERCENTAGE",
                ),
                subscribers=[budgets.CfnBudget.SubscriberProperty(subscription_type="EMAIL", address=alert_email)],
            )

        budgets.CfnBudget(
            self,
            "MonthlyCostBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(amount=monthly_limit_usd, unit="USD"),
            ),
            notifications_with_subscribers=[
                _notification("ACTUAL", 80),      # actually spent 80% of the limit
                _notification("FORECASTED", 100),  # on pace to exceed the limit this month
            ],
        )
