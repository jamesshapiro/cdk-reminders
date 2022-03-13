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
    aws_certificatemanager as certificatemanager,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_route53 as route53,
    aws_route53_targets as route53_targets,
    Aws, CfnOutput, Duration,
    aws_s3 as s3,
)
import aws_cdk as cdk

from constructs import Construct

class CdkRemindersAppStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        with open(".cdk-params") as f:
            lines = f.read().splitlines()
            # .cdk-params should be of the form: key_name=value
            subdomain = [line for line in lines if line.startswith('subdomain=')][0].split('=')[1]
            hosted_zone_id = [line for line in lines if line.startswith('hosted_zone_id=')][0].split('=')[1]
            phone_number = [line for line in lines if line.startswith('NotificationPhone')][0].split('=')[1]
            email = [line for line in lines if line.startswith('NotificationEmail')][0].split('=')[1]
        #phone_number = CfnParameter(self, 'NotificationPhone', 
        #    description="Phone number to receive reminders. For US numbers, should be of the form +12223334444 with +1 as the country code.")
        #email = CfnParameter(self,'NotificationEmail', description="Email to receive reminders.")
        ddb_table = dynamodb.Table(
            self, "Table",
            partition_key=dynamodb.Attribute(name="PK1", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK1", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST
        )
        CfnOutput(self, "DDBTableName", value=ddb_table.table_name)

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
            timeout=Duration.seconds(30),
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
                "REMINDERS_PHONE_NUMBER": phone_number
            },
            timeout=Duration.seconds(30),
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
                timeout=Duration.seconds(30),
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
            value = f'https://{api.rest_api_id}.execute-api.{Aws.REGION}.amazonaws.com/prod/'
        )

        ######## FRONT-END PRIVATE WEBSITE ########
        zone = route53.HostedZone.from_hosted_zone_attributes(self, "HostedZone",
            hosted_zone_id=hosted_zone_id,
            zone_name=subdomain
        )

        site_bucket = s3.Bucket(
            self, f'{subdomain}-bucket',
        )
        certificate = certificatemanager.DnsValidatedCertificate(
            self, f'{subdomain}-certificate',
            domain_name=subdomain,
            hosted_zone=zone,
            subject_alternative_names=[f'www.{subdomain}']
        )

        # authorizer_lambda_policy = iam.PolicyStatement(
        #     self, 'root',
        #     statements=[
        #         iam.PolicyStatement(
        #             actions=['iam:GetRole*'],
        #             resources=[f'arn:aws:iam::{Aws.ACCOUNT_ID}:role/{Aws.STACK_NAME}-AuthorizerFnServiceRole*']
        #         ),
        #         # TODO: limit PassRole to the ec2 role
        #         iam.PolicyStatement(
        #             actions=['dynamodb:GetItem'],
        #             resources=[ddb_table.table_arn]
        #         ),
                
        #     ]
        # )

        AUTHORIZER_FUNCTION_NAME = 'Authorizer'
        
        domain_names = [subdomain, f'www.{subdomain}']
        authorizer_function = cloudfront.experimental.EdgeFunction(self, AUTHORIZER_FUNCTION_NAME,
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset('lambda_edge'),
            handler='authorizer.lambda_handler',
        )
        statement_1 = iam.PolicyStatement(
            actions=['iam:GetRole*','iam:ListRolePolicies'],
            resources=[f'arn:aws:iam::{Aws.ACCOUNT_ID}:role/{Aws.STACK_NAME}-{AUTHORIZER_FUNCTION_NAME}FnServiceRole*']
        )
        statement_2 = iam.PolicyStatement(
            actions=['dynamodb:GetItem'],
            resources=[ddb_table.table_arn]
        )

        #authorizer_function.role.attach_inline_policy(authorizer_lambda_policy)
        authorizer_function.add_to_role_policy(statement_1)
        authorizer_function.add_to_role_policy(statement_2)
        
        #     DistributionAuthorizerRole:
        #   Policies:
        #     - PolicyName: root
        #         Statement:
        #           - Effect: Allow
        #             Action: iam:GetRole*
        #             Resource: !Sub arn:aws:iam::${AWS::AccountId}:role/${AWS::StackName}-DistributionAuthorizerRole-*

        
        distribution = cloudfront.Distribution(
            self, f'{subdomain}-distribution',
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(site_bucket),
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                edge_lambdas=[
                    cloudfront.EdgeLambda(
                        function_version=authorizer_function.current_version,
                        event_type=cloudfront.LambdaEdgeEventType.VIEWER_REQUEST
                    )
                ]
            ),
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(30)
                )
            ],
            comment=f'{subdomain} S3 HTTPS',
            default_root_object='index.html',
            domain_names=domain_names,
            certificate=certificate
        )

        CfnOutput(self, f'{subdomain}-cf-distribution', value=distribution.distribution_id)
        a_record_target = route53.RecordTarget.from_alias(route53_targets.CloudFrontTarget(distribution))
        route53.ARecord(
            self, f'{subdomain}-alias-record',
            zone=zone,
            target=a_record_target,
            record_name=subdomain
        )
        CfnOutput(self, f'{subdomain}-bucket-name', value=site_bucket.bucket_name)
        