from aws_cdk import (
    Stack,
        # Duration,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_apigateway as apigateway,
    # aws_lambda_python_alpha as lambda_python
    # aws_sqs as sqs,
)
import aws_cdk as cdk
import os

from constructs import Construct

class CdkRemindersAppStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ddb_table = dynamodb.Table(
            self, "Table",
            partition_key=dynamodb.Attribute(name="PK1", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK1", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST
        )

        ulid_layer = lambda_.LayerVersion(
            self,
            "Ulid38Layer",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            code=lambda_.Code.from_asset('resources/my-Python38-ulid.zip'),
            compatible_architectures=[lambda_.Architecture.X86_64]
        )

        reminder_creator_function_cdk = lambda_.Function(
            self, "ReminderCreatorCDK",
            runtime=lambda_.Runtime.PYTHON_3_8,
            code=lambda_.Code.from_asset("resources"),
            handler="create_reminder.lambda_handler",
            environment=dict(
                REMINDERS_DDB_TABLE=ddb_table.table_name
            ),
            layers=[ulid_layer]
        )

        api = apigateway.RestApi(
            self,
            "reminders-api-cdk",
            rest_api_name="reminders-api-cdk",
            description="Reminder service in CDK."
        )

        create_reminder_integration = apigateway.LambdaIntegration(
            reminder_creator_function_cdk,
            request_templates={"application/json": '{ "statusCode": "200" }'}
        )

        api.root.add_method("POST", create_reminder_integration)

        ddb_table.grant_write_data(reminder_creator_function_cdk)

