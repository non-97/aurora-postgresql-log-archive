import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import { BaseConstructProps, BaseConstruct } from "./base-construct";
import {
  TargetDbClusterProperty,
  LogDestinationProperty,
  SchedulerProperty,
} from "../../parameter";

export interface SchedulerConstructProps
  extends SchedulerProperty,
    TargetDbClusterProperty,
    LogDestinationProperty,
    BaseConstructProps {
  stateMachine: cdk.aws_stepfunctions.IStateMachine;
}

export class SchedulerConstruct extends BaseConstruct {
  constructor(scope: Construct, id: string, props: SchedulerConstructProps) {
    super(scope, id, props);

    // Role
    const role = new cdk.aws_iam.Role(this, "Role", {
      assumedBy: new cdk.aws_iam.ServicePrincipal("scheduler.amazonaws.com"),
      inlinePolicies: {
        InvokeFunction: new cdk.aws_iam.PolicyDocument({
          statements: [
            new cdk.aws_iam.PolicyStatement({
              effect: cdk.aws_iam.Effect.ALLOW,
              resources: [props.stateMachine.stateMachineArn],
              actions: ["states:StartExecution"],
            }),
          ],
        }),
      },
    });

    // EventBridge Scheduler Group
    const scheduleGroup = new cdk.aws_scheduler.CfnScheduleGroup(
      this,
      "ScheduleGroup"
    );

    // EventBridge Scheduler
    const schedule = new cdk.aws_scheduler.CfnSchedule(this, "Default", {
      flexibleTimeWindow: {
        mode: "OFF",
      },
      groupName: scheduleGroup.ref,
      scheduleExpression: props.scheduleExpression,
      target: {
        arn: props.stateMachine.stateMachineArn,
        roleArn: role.roleArn,
        input: JSON.stringify({
          DbClusterIdentifier: props.dbClusterIdentifier,
          LogDestinationBucket: props.bucketName,
          LogRangeMinutes: props.logRangeMinutes,
        }),
        retryPolicy: {
          maximumEventAgeInSeconds: 60,
          maximumRetryAttempts: 0,
        },
      },
      scheduleExpressionTimezone: "Asia/Tokyo",
      state: "ENABLED",
    });
  }
}
