#!/usr/bin/env python3
import os
import jsii

import aws_cdk as cdk

from aws_cdk import (
    Aspects,
    CfnResource,
)

from cdk_reminders.cdk_reminders_stack import CdkRemindersAppStack

@jsii.implements(cdk.IAspect)
class ForceDeletion:
    def visit(self, scope):
        if isinstance(scope, CfnResource):
            scope.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

app = cdk.App()
my_stack = CdkRemindersAppStack(app, "CdkRemindersParam",
    env={'region': 'us-east-1'}
)

Aspects.of(my_stack).add(ForceDeletion())

app.synth()
