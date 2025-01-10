import * as cdk from "aws-cdk-lib";
import { LambdaProperty } from "../types";

export const lambdaConfig: LambdaProperty = {
  functionApplicationLogLevel: cdk.aws_lambda.ApplicationLogLevel.INFO,
  functionSystemLogLevel: cdk.aws_lambda.SystemLogLevel.INFO,
  enableCompression: "true",
};
