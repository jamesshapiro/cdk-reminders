from aws_cdk import (
    Stack,
        # Duration,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_apigateway as apigateway,
    aws_events as events,
    aws_events_targets as targets,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_iam as iam,
    # aws_lambda_python_alpha as lambda_python
    # aws_sqs as sqs,
)
import aws_cdk as cdk
import os

from constructs import Construct

phone_number = os.environ['NotificationPhone']
email = os.environ['NotificationEmail']

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
            code=lambda_.Code.from_asset('layers/my-Python38-ulid.zip'),
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
            timeout=cdk.Duration.seconds(30),
            memory_size=128,
            layers=[ulid_layer]
        )

        topic = sns.Topic(self, "ReminderCDKTopic")

        reminder_sender_function_cdk = lambda_.Function(
            self, "ReminderSenderCDK",
            runtime=lambda_.Runtime.PYTHON_3_8,
            code=lambda_.Code.from_asset("resources"),
            handler="send_reminders.lambda_handler",
            environment=dict(
                REMINDERS_DDB_TABLE=ddb_table.table_name,
                REMINDERS_TOPIC = topic.topic_arn,
                # TODO: turn this into a formal parameter
                REMINDERS_PHONE_NUMBER = phone_number
                # TODO: turn this into a formal parameter
            ),
            timeout=cdk.Duration.seconds(30),
            memory_size=128,
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

        lambda_target = targets.LambdaFunction(reminder_sender_function_cdk)

        cron_rule = events.Rule(self, "ScheduleRule",
            schedule=events.Schedule.cron(minute="*", hour="*"),
            targets=[lambda_target]
        )

        topic.grant_publish(reminder_sender_function_cdk)
        email_address = email
        #my_topic.add_subscription(subscriptions.EmailSubscription(email_address.value_as_string))
        topic.add_subscription(subscriptions.EmailSubscription(email_address))
        reminder_sender_function_cdk.role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSNSFullAccess"))

        api.root.add_method("POST", create_reminder_integration)

        ddb_table.grant_write_data(reminder_creator_function_cdk)
        ddb_table.grant_read_write_data(reminder_sender_function_cdk)
