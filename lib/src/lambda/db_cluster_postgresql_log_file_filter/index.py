import sys
import os
from typing import Dict, Any, List
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from db_cluster_postgresql_log_file_filter_constants import DEFAULT_LOG_RANGE_MINUTES
from db_cluster_postgresql_log_file_filter import (
    DbClusterPostgreSqlLogFileFilter,
    LogFileFilterConfig,
    LogFile,
)

logger = Logger()
tracer = Tracer()


@logger.inject_lambda_context()
@tracer.capture_lambda_handler
def lambda_handler(
    event: Dict[str, Any], context: LambdaContext
) -> List[Dict[str, Any]]:
    """Lambda関数のハンドラー

    Args:
        event (Dict[str, Any]): Lambda関数のイベントデータ
            必須キー
                - DbClusterIdentifier (str): Aurora DBクラスター識別子
                - LogDestinationBucket (str): ログファイルの出力先S3バケット名
            オプションキー：
                - LogRangeMinutes (int): 現在時刻からさかのぼって取得するログの期間（分）
                    デフォルト: 180 (3時間)
        context (LambdaContext): Lambda実行コンテキスト

    Returns:
        List[Dict[str, Any]]: 処理対象となるログファイル情報のリスト

    Raises:
        SystemExit: 予期しないエラーが発生した場合
    """
    try:
        logger.debug("Processing event", extra={"event": event})
        config = LogFileFilterConfig(
            db_cluster_identifier=event.get("DbClusterIdentifier"),
            log_destination_bucket=event.get("LogDestinationBucket"),
            log_range_minutes=event.get("LogRangeMinutes", DEFAULT_LOG_RANGE_MINUTES),
            compression_enabled=os.environ.get("ENABLE_COMPRESSION", "false").lower()
            == "true",
        )

        db_cluster_postgresql_log_file_filter = DbClusterPostgreSqlLogFileFilter(config)
        result: LogFile = (
            db_cluster_postgresql_log_file_filter.filter_cluster_log_files()
        )

        logger.info(
            "Lambda execution completed",
            extra={
                "processed_logs": result,
                "compression_enabled": config.compression_enabled,
            },
        )
        return result

    except Exception as e:
        logger.exception("Unexpected error", error=str(e))
        sys.exit(1)
