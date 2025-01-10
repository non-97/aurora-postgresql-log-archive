import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import { BaseConstructProps, BaseConstruct } from "./base-construct";
import { LambdaConstruct } from "./lambda-construct";
import { LambdaProperty, LogDestinationProperty } from "../../parameter";

export interface WorkflowProps
  extends LambdaProperty,
    LogDestinationProperty,
    BaseConstructProps {
  lambdaConstruct: LambdaConstruct;
}

export class WorkflowConstruct extends BaseConstruct {
  readonly stateMachine: cdk.aws_stepfunctions.IStateMachine;
  constructor(scope: Construct, id: string, props: WorkflowProps) {
    super(scope, id, props);

    const dbClusterPostgreSqlLogFileFilter =
      new cdk.aws_stepfunctions_tasks.LambdaInvoke(
        this,
        "DbClusterPostgreSqlLogFileFilter",
        {
          lambdaFunction:
            props.lambdaConstruct.dbClusterPostgreSqlLogFileFilter,
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

    const rdsLogFileUploader = new cdk.aws_stepfunctions_tasks.LambdaInvoke(
      this,
      "RdsLogFileUploader",
      {
        lambdaFunction: props.lambdaConstruct.rdsLogFileUploader,
        payload: cdk.aws_stepfunctions.TaskInput.fromObject({
          DbInstanceIdentifier: cdk.aws_stepfunctions.JsonPath.stringAt(
            "$.DbInstanceIdentifier"
          ),
          LogDestinationBucket: cdk.aws_stepfunctions.JsonPath.stringAt(
            "$.LogDestinationBucket"
          ),
          LastWritten: cdk.aws_stepfunctions.JsonPath.stringAt("$.LastWritten"),
          LogFileName: cdk.aws_stepfunctions.JsonPath.stringAt("$.LogFileName"),
          ObjectKey: cdk.aws_stepfunctions.JsonPath.stringAt("$.ObjectKey"),
        }),
      }
    );

    const map = new cdk.aws_stepfunctions.Map(this, "Map", {
      itemsPath: "$.Payload",
      maxConcurrency: 30,
      resultPath: "$.Output",
    });

    const stateMachine = new cdk.aws_stepfunctions.StateMachine(
      this,
      "testStateMachine",
      {
        definitionBody: cdk.aws_stepfunctions.DefinitionBody.fromChainable(
          dbClusterPostgreSqlLogFileFilter.next(
            map.itemProcessor(rdsLogFileUploader)
          )
        ),
        tracingEnabled: true,
      }
    );

    this.stateMachine = stateMachine;
  }
}
