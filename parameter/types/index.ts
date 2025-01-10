import * as cdk from "aws-cdk-lib";

export interface TargetDbClusterProperty {
  dbClusterIdentifier: string;
  logRangeMinutes: number;
}

export interface LogDestinationProperty {
  bucketName: string;
  logGroupPrefix?: string;
}

export interface LogRouting {
  enableLogRouting?: boolean;
  enableLogType?: ("error " | "slow_query" | "audit" | "connection")[];
}

export interface LambdaProperty {
  functionApplicationLogLevel?: cdk.aws_lambda.ApplicationLogLevel;
  functionSystemLogLevel?: cdk.aws_lambda.SystemLogLevel;
  powertoolsLogLevel?: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  uploaderMemorySize?: number;
  uploaderTimeout?: cdk.Duration;
  uploaderEphemeralStorageSize?: cdk.Size;
  enableCompression?: "true" | "false";
}

export interface SchedulerProperty {
  scheduleExpression: string;
}

export interface AuroraPostgreSqlLogArchiveProperty {
  lambdaProperty: LambdaProperty;
  targetDbClusterProperty: TargetDbClusterProperty;
  logDestinationProperty: LogDestinationProperty;
  schedulerProperty?: SchedulerProperty;
}

export interface AuroraPostgreSqlLogArchiveStackProperty {
  env?: cdk.Environment;
  props: AuroraPostgreSqlLogArchiveProperty;
}
