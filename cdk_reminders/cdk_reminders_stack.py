from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_apigateway as apigateway,
    aws_events as events,
    aws_events_targets as targets,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_iam as iam,
    aws_logs as logs,
    custom_resources as custom_resources,
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

        api.root.add_method("POST", create_reminder_integration, api_key_required=True)
        api_key = api.add_api_key('cdk-reminders-api-key')
        usage_plan = api.add_usage_plan(
            'cdk-reminders-usage-plan'
        )
        usage_plan.add_api_key(api_key)
        usage_plan.add_api_stage(stage=api.deployment_stage)

        ddb_table.grant_write_data(reminder_creator_function_cdk)
        ddb_table.grant_read_write_data(reminder_sender_function_cdk)

        # custom_resources_role = iam.Role(self, "Role",
        #     assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        #     description="Example role..."
        # )

        #api_key.grant_read(custom_resources_role)

        # do_nothing_function = lambda_.Function(
        #     self, "RemindersCDKDoNothing",
        #     runtime=lambda_.Runtime.PYTHON_3_8,
        #     code=lambda_.Code.from_asset("resources"),
        #     handler="do_nothing.lambda_handler",
        #     timeout=cdk.Duration.seconds(30),
        #     memory_size=128,
        # )

        with open('resources/custom_resource.py') as f:
            is_complete_code = f.read()

        is_complete_handler=lambda_.Function(
                self, 
                id="ReminderCustomResourceCDK",
                runtime=lambda_.Runtime.PYTHON_3_8,
                code=lambda_.Code.from_inline(is_complete_code),
                handler="index.lambda_handler",
                log_retention=logs.RetentionDays.ONE_DAY,
                environment=dict(
                    API_KEY_ID=api_key.key_id,
                ),
                timeout=cdk.Duration.seconds(30),
                memory_size=128,
                #role=custom_resources_role
            )

        api_key.grant_read(is_complete_handler)

        my_provider = custom_resources.Provider(
            self, "MyProvider",
            on_event_handler=is_complete_handler,
            is_complete_handler=is_complete_handler,
            #timeout=cdk.Duration.minutes(30),
            #total_timeout=cdk.Duration.minutes(30)
        )

        custom_resource = cdk.CustomResource(
            scope=self,
            id='MyCustomResource',
            service_token=my_provider.service_token,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            resource_type="Custom::JamesResource",
        )

        cdk.CfnOutput(
            self, "APIKeyValue",
            description="API Key Value",
            value = custom_resource.get_att_string("APIKeyValue")
        )

        cdk.CfnOutput(
            self, "ReminderApi",
            description="Reminder Api",
            value = f'https://{api.rest_api_id}.execute-api.us-east-1.amazonaws.com/prod/'
        )

        

        # my_provider = custom_resources.Provider(self, "MyProvider",
        #     on_event_handler=on_event,
        #     log_retention=logs.RetentionDays.ONE_DAY,  # default is INFINITE
        #     role=custom_resources_role
        # )

        # resource = MyCustomResource(
        #     self, "MyCustomResource",
        #     api_key_arn=api_key.key_arn,
        #     api_key_id=api_key.key_id
        # )
