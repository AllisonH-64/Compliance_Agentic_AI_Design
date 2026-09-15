from aws_cdk import (
    RemovalPolicy,
    Stack,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
)
from constructs import Construct


class DataStack(Stack):
    """Stateful resources: DynamoDB tables, the audit-export S3 bucket, and the
    Cognito user pool. Kept separate from ApiStack per CDK best practice -- losing
    any of these is data loss or every user getting logged out, so they must never
    be replaced as a side effect of an unrelated Lambda/API Gateway change."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Current-state tables. Mirror app/storage_sqlite.py's decisions/reviews
        # tables 1:1 -- a single json-blob attribute per item, not exploded into
        # native DynamoDB attributes, so app/storage_common.py's deserialization
        # logic stays reusable unchanged across both backends.
        self.decisions_table = dynamodb.Table(
            self,
            "DecisionsTable",
            partition_key=dynamodb.Attribute(name="case_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.reviews_table = dynamodb.Table(
            self,
            "ReviewsTable",
            partition_key=dynamodb.Attribute(name="case_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Append-only audit tables. DynamoDB has no autoincrement, so the sort key
        # is "{recorded_at}#{uuid}" (see app/storage_dynamodb.py) rather than the
        # SQLite backend's AUTOINCREMENT event_id. Streams feed the audit-export
        # Lambda in ApiStack, which archives every event to S3.
        self.decision_history_table = dynamodb.Table(
            self,
            "DecisionHistoryTable",
            partition_key=dynamodb.Attribute(name="case_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="event_key", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
            stream=dynamodb.StreamViewType.NEW_IMAGE,
        )

        self.review_history_table = dynamodb.Table(
            self,
            "ReviewHistoryTable",
            partition_key=dynamodb.Attribute(name="case_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="event_key", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
            stream=dynamodb.StreamViewType.NEW_IMAGE,
        )

        # Immutable audit archive. RETAIN with no auto-delete is a deliberate
        # departure from the usual "clean teardown" default for dev/demo buckets --
        # this one must survive `cdk destroy` since it's the durable audit trail.
        self.audit_bucket = s3.Bucket(
            self,
            "AuditExportBucket",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.user_pool = cognito.UserPool(
            self,
            "UserPool",
            self_sign_up_enabled=False,  # accounts are provisioned by a compliance_manager, not open sign-up
            sign_in_aliases=cognito.SignInAliases(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=False),
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.user_pool_client = self.user_pool.add_client(
            "ApiClient",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL],
            ),
        )

        # One Cognito Group per UserRole (app/models.py). Names must match exactly:
        # app/main.py's get_current_user() reads the first "cognito:groups" entry on
        # the token as the role claim. The loop only ever produces these 4 fixed,
        # hardcoded values -- not user/runtime input -- so the resulting construct
        # IDs are stable across every deploy, which is why interpolating into the
        # construct ID here is safe (see CDK guidance on stable logical IDs).
        for role_name in ("employee", "compliance_analyst", "compliance_manager", "auditor"):
            cognito.CfnUserPoolGroup(
                self,
                f"{role_name.title().replace('_', '')}Group",
                user_pool_id=self.user_pool.user_pool_id,
                group_name=role_name,
            )
