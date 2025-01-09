import sys
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

# 定数定義
LOG_FILENAME_PATTERN = r"postgresql\.log\.\d{4}-\d{2}-\d{2}-\d{4}$"
MAX_WORKERS = 4
DEFAULT_LOG_RANGE_MINUTES = 180


# Lambda Powertoolsの設定
logger = Logger()
tracer = Tracer()


@dataclass(frozen=True)
class LogFile:
    """ログファイル情報を表すデータクラス"""

    DbInstanceIdentifier: str
    LogDestinationBucket: str
    LastWritten: int
    LogFileName: str
    ObjectKey: str

    def to_dict(self) -> Dict[str, Any]:
        """辞書型に変換"""
        return {
            "DbInstanceIdentifier": self.DbInstanceIdentifier,
            "LogDestinationBucket": self.LogDestinationBucket,
            "LastWritten": self.LastWritten,
            "LogFileName": self.LogFileName,
            "ObjectKey": self.ObjectKey,
        }


@dataclass(frozen=True)
class LogDestinationConfig:
    """イベントから設定値を取得するデータクラス"""

    db_cluster_identifier: str
    log_destination_bucket: str
    log_range_minutes: int = DEFAULT_LOG_RANGE_MINUTES

    def __post_init__(self) -> None:
        """初期化後のバリデーション"""
        if not self.db_cluster_identifier:
            raise ValueError("DbClusterIdentifier is required")
        if not self.log_destination_bucket:
            raise ValueError("LogDestinationBucket is required")
        if self.log_range_minutes <= 0:
            raise ValueError("LogRangeMinutes must be greater than 0")


class DbClusterPostgreSqlLogFilter:
    """DBクラスターログ処理クラス"""

    def __init__(self, config: LogDestinationConfig):
        self.config = config
        self.logger = logger
        self.rds_client = boto3.client("rds")
        self.s3_client = boto3.client("s3")

    @tracer.capture_method
    def get_db_instances(self) -> List[str]:
        """DBクラスターに属するDBインスタンス一覧を取得

        Returns:
            List[str]: DBインスタンス識別子のリスト

        Raises:
            ValueError: DBクラスターが見つからない場合
            ClientError: AWS APIの呼び出しに失敗した場合
        """

        try:
            self.logger.debug(
                "Retrieving DB instances",
                extra={"cluster_id": self.config.db_cluster_identifier},
            )

            # DBクラスター内のDBインスタンス一覧を取得
            response = self.rds_client.describe_db_clusters(
                DBClusterIdentifier=self.config.db_cluster_identifier
            )

            if not response["DBClusters"]:
                self.logger.error(
                    "DB cluster not found",
                    extra={"cluster_id": self.config.db_cluster_identifier},
                )
                raise ValueError(
                    f"DBクラスター {self.config.db_cluster_identifier} が見つかりません"
                )

            instances = [
                member["DBInstanceIdentifier"]
                for member in response["DBClusters"][0]["DBClusterMembers"]
            ]

            self.logger.info(
                "Retrieved DB instances",
                extra={
                    "cluster_id": self.config.db_cluster_identifier,
                    "instance_ids": instances,
                    "instance_count": len(instances),
                },
            )
            return instances

        except ClientError as e:
            self.logger.exception(
                "Failed to get DB cluster information",
                extra={"cluster_id": self.config.db_cluster_identifier},
                error=str(e),
            )
            raise

    @tracer.capture_method
    def get_log_files(self, db_instance: str) -> List[Dict[str, Any]]:
        """指定されたDBインスタンスのログファイル一覧の取得

        Args:
            db_instance (str): DBインスタンス識別子

        Returns:
            List[Dict[str, Any]]: ログファイル情報のリスト。各要素には以下のキーが含まれる
                - DbInstanceIdentifier (str): DBインスタンス識別子
                - LastWritten (int): 最終更新のUNIXタイムスタンプ
                - LogFileName (str): ログファイル名
                - Size (int): ファイルサイズ（バイト）

        Raises:
            ClientError: AWS APIの呼び出しに失敗した場合
        """

        try:
            # 現在時刻から指定分前までの時間範囲を計算
            current_time = datetime.now()
            time_threshold = int(
                (
                    current_time - timedelta(minutes=self.config.log_range_minutes)
                ).timestamp()
                * 1000
            )

            self.logger.debug(
                "Retrieving log files",
                extra={"db_instance": db_instance, "time_threshold": time_threshold},
            )

            # postgresql.log を含むDBインスタンスのログファイルを取得
            response = self.rds_client.describe_db_log_files(
                DBInstanceIdentifier=db_instance,
                FilenameContains="postgresql.log",
                FileLastWritten=time_threshold,
            )

            log_files = [
                {
                    **log_file,
                    "DbInstanceIdentifier": db_instance,
                    "LogDestinationBucket": self.config.log_destination_bucket,
                }
                for log_file in response["DescribeDBLogFiles"]
            ]

            self.logger.info(
                "Retrieved log files",
                extra={"db_instance": db_instance, "log_file_count": len(log_files)},
            )
            return log_files

        except ClientError as e:
            self.logger.exception(
                "Failed to get log files",
                extra={"db_instance": db_instance},
                error=str(e),
            )
            raise

    @tracer.capture_method
    def check_object_exists(self, object_key: str) -> bool:
        """S3バケット内の指定されたオブジェクトの存在確認

        Args:
            object_key (str): 確認するS3オブジェクトのキー

        Returns:
            bool: オブジェクトが存在する場合はTrue、存在しない場合はFalse

        Raises:
            ClientError: S3 APIの呼び出しに失敗した場合（404エラーを除く）
        """

        try:
            self.logger.debug(
                "Checking object existence",
                extra={
                    "bucket": self.config.log_destination_bucket,
                    "object_key": object_key,
                },
            )
            self.s3_client.head_object(
                Bucket=self.config.log_destination_bucket, Key=object_key
            )
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            self.logger.exception(
                "Failed to check object existence",
                extra={
                    "bucket": self.config.log_destination_bucket,
                    "object_key": object_key,
                },
                error=str(e),
            )
            raise

    @tracer.capture_method
    def filter_log_files(self, log_files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """ログファイルリストのフィルタリング

        以下の条件でフィルタリングを行う
        1. ファイル名が正規表現パターンLOG_FILENAME_PATTERNにマッチする
        2. 最終更新時刻が最新のファイルを除外

        Args:
            log_files (List[Dict[str, Any]]): フィルタリング対象のログファイルリスト

        Returns:
            List[Dict[str, Any]]: フィルタリング後のログファイルリスト
        """

        if not log_files:
            return []

        pattern = re.compile(LOG_FILENAME_PATTERN)

        # LOG_FILENAME_PATTERN にマッチするログファイルのみ抽出
        valid_logs = [log for log in log_files if pattern.search(log["LogFileName"])]

        self.logger.debug(
            "Filtered valid log files",
            extra={
                "total_logs_count": len(log_files),
                "valid_logs_count": len(valid_logs),
            },
        )

        if not valid_logs:
            return []

        # 最終書き込み日時が最新のものを除外
        latest_written = max(valid_logs, key=lambda x: x["LastWritten"])["LastWritten"]

        filtered_logs = [
            log for log in valid_logs if log["LastWritten"] < latest_written
        ]

        self.logger.info(
            "Completed log filtering",
            extra={
                "total_logs_count": len(log_files),
                "filtered_logs_count": len(filtered_logs),
            },
        )
        return filtered_logs

    @tracer.capture_method
    def generate_object_key(self, db_instance: str, log_filename: str) -> Optional[str]:
        """ログファイルのS3オブジェクトキーの生成

        Args:
            db_instance (str): DBインスタンス識別子
            log_filename (str): ログファイル名

        Returns:
            Optional[str]: 生成されたS3オブジェクトキー
                ファイル名のパース失敗時はNone

        Example:
            >>> generate_object_key("db-instance-1", "postgresql.log.2024-01-01-0000")
            "cluster-name/db-instance-1/raw/2024/01/01/00/postgresql.log.2024-01-01-0000"
        """

        try:
            date_part = log_filename.split(".")[-1]
            date_obj = datetime.strptime(date_part, "%Y-%m-%d-%H%M")

            object_key = (
                f"{self.config.db_cluster_identifier}/"
                f"{db_instance}/raw/"
                f"{date_obj.strftime('%Y/%m/%d/%H')}/"
                f"postgresql.log.{date_part}"
            )

            self.logger.debug(
                "Generated object key",
                extra={
                    "db_instance": db_instance,
                    "log_filename": log_filename,
                    "object_key": object_key,
                },
            )
            return object_key

        except ValueError as e:
            self.logger.warning(
                "Failed to generate object key",
                extra={"db_instance": db_instance, "log_filename": log_filename},
                error=str(e),
            )
            return None

    @tracer.capture_method
    def filter_instance_logs(self, db_instance: str) -> List[LogFile]:
        """指定されたDBインスタンスのログファイルの処理

        以下の処理の実施
        1. ログファイル一覧の取得
        2. フィルタリング
        3. S3オブジェクトの存在確認
        4. 結果のLogFileオブジェクト生成

        Args:
            db_instance (str): 処理対象のDBインスタンス識別子

        Returns:
            List[LogFile]: 処理対象となるログファイル情報のリスト

        Raises:
            ClientError: AWS APIの呼び出しに失敗した場合
        """

        self.logger.info("Processing instance logs", extra={"db_instance": db_instance})

        log_files = self.get_log_files(db_instance)
        filtered_logs = self.filter_log_files(log_files)
        result_logs = []

        for log_file in filtered_logs:
            object_key = self.generate_object_key(db_instance, log_file["LogFileName"])

            if not object_key:
                continue

            if not self.check_object_exists(object_key):
                result_logs.append(
                    LogFile(
                        DbInstanceIdentifier=log_file["DbInstanceIdentifier"],
                        LastWritten=log_file["LastWritten"],
                        LogFileName=log_file["LogFileName"],
                        LogDestinationBucket=log_file["LogDestinationBucket"],
                        ObjectKey=object_key,
                    )
                )

        self.logger.info(
            "Completed instance log processing",
            extra={"db_instance": db_instance, "processed_logs": len(result_logs)},
        )
        return result_logs

    @tracer.capture_method
    def filter_cluster_logs(self) -> List[Dict[str, Any]]:
        """DBクラスター全体のログファイルの処理

        クラスター内の全DBインスタンスのログを並列で処理し、S3にアップロードされていないログファイルの情報を返す

        Returns:
            List[Dict[str, Any]]: 処理対象となるログファイル情報の辞書のリスト
                各辞書には以下のキーが含まれる
                    - DbInstanceIdentifier (str): DBインスタンス識別子
                    - LastWritten (int): 最終更新のUNIXタイムスタンプ
                    - LogFileName (str): ログファイル名
                    - ObjectKey (str): アップロード先のS3オブジェクトキー

        Raises:
            Exception: 処理中に発生した任意の例外
        """

        try:
            db_instances = self.get_db_instances()

            self.logger.info(
                "Starting log processing",
                extra={
                    "cluster_id": self.config.db_cluster_identifier,
                    "instance_count": len(db_instances),
                },
            )

            all_logs = []

            # ThreadPoolExecutorで並行処理を実行
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                # 各DBインスタンスに対して並行でログ処理を実行
                future_to_instance = {
                    executor.submit(self.filter_instance_logs, db_instance): db_instance
                    for db_instance in db_instances
                }

                # 完了したタスクの結果を収集
                for future in future_to_instance:
                    instance = future_to_instance[future]
                    try:
                        logs = future.result()
                        all_logs.extend(logs)
                    except Exception as e:
                        self.logger.exception(
                            "Failed to process instance logs",
                            extra={"db_instance": instance},
                            error=str(e),
                        )
                        raise

            self.logger.info(
                "Completed log processing", extra={"total_logs_count": len(all_logs)}
            )
            return [log.to_dict() for log in all_logs]

        except Exception as e:
            self.logger.exception("Error in process", error=str(e))
            raise


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
        config = LogDestinationConfig(
            db_cluster_identifier=event.get("DbClusterIdentifier"),
            log_destination_bucket=event.get("LogDestinationBucket"),
            log_range_minutes=event.get("LogRangeMinutes", DEFAULT_LOG_RANGE_MINUTES),
        )

        db_cluster_postgresql_log_filter = DbClusterPostgreSqlLogFilter(config)
        result = db_cluster_postgresql_log_filter.filter_cluster_logs()

        logger.info("Lambda execution completed", extra={"processed_logs": result})
        return result

    except Exception as e:
        logger.exception("Unexpected error", error=str(e))
        sys.exit(1)
