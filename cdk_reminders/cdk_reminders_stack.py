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
    custom_resources as custom_resources,
    CfnParameter,
)
import aws_cdk as cdk

from constructs import Construct

class CdkRemindersAppStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # with open(".cdk-params") as f:
        #     lines = f.read().splitlines()
        #     # .cdk-params should be of the form (note the required country code in phone #):
        #     # NotificationPhone=+12223334444
        #     # NotificationEmail=jeff@example.com
        #     phone_number = [line for line in lines if line.startswith('NotificationPhone')][0].split('=')[1]
        #     email = [line for line in lines if line.startswith('NotificationEmail')][0].split('=')[1]
        phone_number = CfnParameter(self, 'NotificationPhone', 
            description="Phone number to receive reminders. For US numbers, should be of the form +12223334444 with +1 as the country code.")
        email = CfnParameter(self,'NotificationEmail', description="Email to receive reminders.")
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
            environment={
                "REMINDERS_DDB_TABLE": ddb_table.table_name,
                "REMINDERS_TOPIC": topic.topic_arn,
                "REMINDERS_PHONE_NUMBER": phone_number.value_as_string
            },
            timeout=cdk.Duration.seconds(30),
            memory_size=128,
            layers=[ulid_layer]
        )

        api = apigateway.RestApi(
            self,
            "reminders-api-cdk",
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
        topic.add_subscription(subscriptions.EmailSubscription(email_address.value_as_string))
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

        with open('resources/custom_resource.py') as f:
            is_complete_code = f.read()

        is_complete_handler=lambda_.Function(
                self, 
                id="ReminderCustomResourceCDK",
                runtime=lambda_.Runtime.PYTHON_3_8,
                code=lambda_.Code.from_inline(is_complete_code),
                handler="index.lambda_handler",
                environment=dict(
                    API_KEY_ID=api_key.key_id,
                ),
                timeout=cdk.Duration.seconds(30),
                memory_size=128
            )

        api_key.grant_read(is_complete_handler)

        my_provider = custom_resources.Provider(
            self, "MyProvider",
            on_event_handler=is_complete_handler,
            is_complete_handler=is_complete_handler
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
