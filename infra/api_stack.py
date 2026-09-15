from pathlib import Path

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_authorizers as apigwv2_authorizers,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_cloudwatch as cloudwatch,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_lambda_event_sources as lambda_event_sources,
    aws_logs as logs,
    aws_s3 as s3,
)
from constructs import Construct

INFRA_DIR = Path(__file__).resolve().parent


class ApiStack(Stack):
    """Stateless resources: the API Lambda (Lambdalith wrapping the existing
    FastAPI app via Mangum -- the right pattern for migrating an existing
    FastAPI app, not a function-per-route rewrite), an HTTP API with a native
    Cognito JWT authorizer, the audit-export Lambda + its DynamoDB Streams
    triggers, and CloudWatch observability. Depends on DataStack via constructor
    props and grant*() calls, never hand-written IAM policy JSON."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        decisions_table: dynamodb.Table,
        reviews_table: dynamodb.Table,
        decision_history_table: dynamodb.Table,
        review_history_table: dynamodb.Table,
        audit_bucket: s3.Bucket,
        user_pool: cognito.UserPool,
        user_pool_client: cognito.UserPoolClient,
        lambda_asset_path: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        issuer = f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}"

        api_log_group = logs.LogGroup(
            self,
            "ApiFunctionLogs",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.api_function = lambda_.Function(
            self,
            "ApiFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.X86_64,
            handler="lambda_handler.handler",
            code=lambda_.Code.from_asset(lambda_asset_path),
            timeout=Duration.seconds(29),  # stay under HTTP API's 30s hard integration timeout
            memory_size=512,
            log_group=api_log_group,
            environment={
                "COMPLIANCE_STORAGE_BACKEND": "dynamodb",
                "COMPLIANCE_DECISIONS_TABLE": decisions_table.table_name,
                "COMPLIANCE_REVIEWS_TABLE": reviews_table.table_name,
                "COMPLIANCE_DECISION_HISTORY_TABLE": decision_history_table.table_name,
                "COMPLIANCE_REVIEW_HISTORY_TABLE": review_history_table.table_name,
                "COMPLIANCE_AUTH_JWKS_URL": f"{issuer}/.well-known/jwks.json",
                "COMPLIANCE_AUTH_ISSUER": issuer,
                "COMPLIANCE_AUTH_AUDIENCE": user_pool_client.user_pool_client_id,
            },
        )

        decisions_table.grant_read_write_data(self.api_function)
        reviews_table.grant_read_write_data(self.api_function)
        decision_history_table.grant_read_write_data(self.api_function)
        review_history_table.grant_read_write_data(self.api_function)

        authorizer = apigwv2_authorizers.HttpJwtAuthorizer(
            "CognitoAuthorizer",
            jwt_issuer=issuer,
            jwt_audience=[user_pool_client.user_pool_client_id],
        )

        self.http_api = apigwv2.HttpApi(
            self,
            "HttpApi",
            default_integration=apigwv2_integrations.HttpLambdaIntegration("ApiIntegration", self.api_function),
            default_authorizer=authorizer,
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],  # tighten to a known origin once a frontend exists
                allow_methods=[apigwv2.CorsHttpMethod.ANY],
                allow_headers=["Authorization", "Content-Type"],
            ),
        )

        # /health stays open -- a liveness check that itself needs a Cognito token
        # to answer defeats the point of a liveness check.
        self.http_api.add_routes(
            path="/health",
            methods=[apigwv2.HttpMethod.GET],
            integration=apigwv2_integrations.HttpLambdaIntegration("HealthIntegration", self.api_function),
            authorizer=apigwv2.HttpNoneAuthorizer(),
        )

        export_log_group = logs.LogGroup(
            self,
            "AuditExportFunctionLogs",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.audit_export_function = lambda_.Function(
            self,
            "AuditExportFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.X86_64,
            handler="audit_export.handler",
            code=lambda_.Code.from_asset(str(INFRA_DIR / "lambda" / "audit_export")),
            timeout=Duration.seconds(60),
            memory_size=256,
            log_group=export_log_group,
            environment={"AUDIT_BUCKET": audit_bucket.bucket_name},
        )

        audit_bucket.grant_write(self.audit_export_function)

        # Poison records must not block a shard for the full 24h stream retention
        # window -- bounded retries + bisect-on-error, per aws-serverless guidance.
        for table in (decision_history_table, review_history_table):
            self.audit_export_function.add_event_source(
                lambda_event_sources.DynamoEventSource(
                    table,
                    starting_position=lambda_.StartingPosition.TRIM_HORIZON,
                    batch_size=100,
                    bisect_batch_on_error=True,
                    retry_attempts=3,
                    report_batch_item_failures=True,
                )
            )

        cloudwatch.Alarm(
            self,
            "ApiFunctionErrorAlarm",
            metric=self.api_function.metric_errors(period=Duration.minutes(5)),
            threshold=1,
            evaluation_periods=1,
            alarm_description="API Lambda is returning errors",
        )
        cloudwatch.Alarm(
            self,
            "ApiFunctionThrottleAlarm",
            metric=self.api_function.metric_throttles(period=Duration.minutes(5)),
            threshold=1,
            evaluation_periods=1,
            alarm_description="API Lambda is being throttled -- concurrency limit reached",
        )
        cloudwatch.Alarm(
            self,
            "ApiFunctionDurationAlarm",
            metric=self.api_function.metric_duration(period=Duration.minutes(5), statistic="p99"),
            threshold=24000,  # ~80% of the 29s function timeout
            evaluation_periods=1,
            alarm_description="API Lambda P99 duration approaching its timeout",
        )
        cloudwatch.Alarm(
            self,
            "AuditExportIteratorAgeAlarm",
            metric=self.audit_export_function.metric(
                metric_name="IteratorAge",
                period=Duration.minutes(5),
                statistic="Maximum",
            ),
            threshold=60000,  # 60s, per aws-serverless minimum-alarm-set guidance
            evaluation_periods=1,
            alarm_description="Audit export Lambda is falling behind the DynamoDB Streams",
        )
