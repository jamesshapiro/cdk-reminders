import aws_cdk as core
import aws_cdk.assertions as assertions

from cdk_reminders.cdk_reminders_stack import CdkRemindersStack

# example tests. To run these tests, uncomment this file along with the example
# resource in cdk_reminders/cdk_reminders_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = CdkRemindersStack(app, "cdk-reminders")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
