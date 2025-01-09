import { AuroraPostgreSqlLogArchiveStackProperty } from "../types";
import { targetDbClusterConfig } from "./db-cluster-config";
import { lambdaConfig } from "./lambda-config";
import { logDestinationConfig } from "./log-destination-config";
import { schedulerConfig } from "./scheduler-config";

export const auroraPostgreSqlLogArchiveStackProperty: AuroraPostgreSqlLogArchiveStackProperty =
  {
    env: {
      account: process.env.CDK_DEFAULT_ACCOUNT,
      region: process.env.CDK_DEFAULT_REGION,
    },
    props: {
      lambdaProperty: lambdaConfig,
      targetDbClusterProperty: targetDbClusterConfig,
      logDestinationProperty: logDestinationConfig,
      schedulerProperty: schedulerConfig,
    },
  };
