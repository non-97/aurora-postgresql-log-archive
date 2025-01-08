import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import { BaseConstructProps, BaseConstruct } from "./base-construct";
import { LambdaConstruct } from "./lambda-construct";
import {
  LambdaProperty,
  DbClusterProperty,
  LogDestinationProperty,
} from "../../parameter";

export interface WorkflowProps
  extends LambdaProperty,
    DbClusterProperty,
    LogDestinationProperty,
    BaseConstructProps {
  lambdaConstruct: LambdaConstruct;
}

export class WorkflowConstruct extends BaseConstruct {
  readonly stateMachine: cdk.aws_stepfunctions.IStateMachine;
  constructor(scope: Construct, id: string, props: WorkflowProps) {
    super(scope, id, props);

    const dbClusterPostgreSqlLogFilter =
      new cdk.aws_stepfunctions_tasks.LambdaInvoke(
        this,
        "DbClusterPostgreSqlLogFilter",
        {
          lambdaFunction: props.lambdaConstruct.dbClusterPostgreSqlLogFilter,
          payload: cdk.aws_stepfunctions.TaskInput.fromObject({
            DbClusterIdentifier: cdk.aws_stepfunctions.JsonPath.stringAt(
              "$.DbClusterIdentifier"
            ),
            LogDestinationBucket: cdk.aws_stepfunctions.JsonPath.stringAt(
              "$.LogDestinationBucket"
            ),
            LogRangeMinutes:
              cdk.aws_stepfunctions.JsonPath.stringAt("$.LogRangeMinutes"),
          }),
        }
      );

    const stateMachine = new cdk.aws_stepfunctions.StateMachine(
      this,
      "testStateMachine",
      {
        definition: dbClusterPostgreSqlLogFilter,
        tracingEnabled: true,
      }
    );

    this.stateMachine = stateMachine;
  }
}
