import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import { LambdaConstruct } from "./construct/lambda-construct";
import { WorkflowConstruct } from "./construct/workflow-construct";
import { AuroraPostgreSqlLogArchiveProperty } from "../parameter/index";

export interface AuroraPostgreSqlLogArchiveStackProperty
  extends cdk.StackProps,
    AuroraPostgreSqlLogArchiveProperty {}

export class AuroraPostgresqlLogArchiveStack extends cdk.Stack {
  constructor(
    scope: Construct,
    id: string,
    props: AuroraPostgreSqlLogArchiveStackProperty
  ) {
    super(scope, id, props);

    const lambdaConstruct = new LambdaConstruct(this, "LambdaConstruct", {
      ...props.lambdaProperty,
      ...props.logDestinationProperty,
    });

    const workflowConstruct = new WorkflowConstruct(this, "WorkflowConstruct", {
      ...props.lambdaProperty,
      ...props.logDestinationProperty,
      lambdaConstruct,
    });
  }
}
