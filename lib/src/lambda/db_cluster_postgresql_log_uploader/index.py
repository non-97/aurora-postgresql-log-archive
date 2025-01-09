import sys
import os
import time
import tempfile
import urllib.request
import urllib.error
from http.client import IncompleteRead
from typing import Dict, Any
import boto3
from botocore.awsrequest import AWSRequest
import botocore.auth as auth
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

# Lambda Powertoolsの設定
logger = Logger()
tracer = Tracer()


class RdsLogDownloader:
    """RDSログをダウンロードするクラス"""

    def __init__(self, region: str = None):
        self.session = boto3.Session(region_name=region)
        self.region = self.session.region_name or os.environ.get(
            "AWS_REGION", "us-east-1"
        )
        self.credentials = self.session.get_credentials()
        self.remote_host = f"rds.{self.region}.amazonaws.com"

    def _get_signed_request(self, url: str) -> urllib.request.Request:
        """署名付きリクエストを作成"""
        sigv4auth = auth.SigV4Auth(self.credentials, "rds", self.region)
        awsreq = AWSRequest(method="GET", url=url)
        sigv4auth.add_auth(awsreq)

        return urllib.request.Request(
            url=url,
            headers={
                "Authorization": awsreq.headers["Authorization"],
                "Host": self.remote_host,
                "X-Amz-Date": awsreq.context["timestamp"],
                "X-Amz-Security-Token": self.credentials.token,
            },
        )

    @tracer.capture_method
    def download_log_file(
        self,
        instance_id: str,
        file_name: str,
        output_path: str,
        retries: int = 3,
        delay: int = 5,
    ) -> bool:
        """
        RDSログファイルをダウンロード

        Args:
            instance_id: DBインスタンス識別子
            file_name: ログファイル名
            output_path: 出力ファイルパス
            retries: リトライ回数
            delay: リトライ間隔（秒）

        Returns:
            bool: ダウンロード成功時True
        """
        base_url = (
            f"https://{self.remote_host}/v13/downloadCompleteLogFile/{instance_id}/"
        )
        current_file_name = file_name

        logger.info(
            "Starting log file download",
            extra={
                "instance_id": instance_id,
                "file_name": file_name,
                "output_path": output_path,
            },
        )

        for attempt in range(retries):
            try:
                url = base_url + current_file_name
                req = self._get_signed_request(url)

                with (
                    urllib.request.urlopen(req) as response,
                    open(output_path, "wb") as out_file,
                ):
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        out_file.write(chunk)

                # ファイルサイズに関係なくダウンロード成功とみなす
                logger.info(
                    "Successfully downloaded log file",
                    extra={
                        "instance_id": instance_id,
                        "file_name": file_name,
                        "size": os.path.getsize(output_path),
                    },
                )
                return True

            except IncompleteRead as e:
                logger.warning(
                    "Incomplete read error",
                    extra={"attempt": attempt + 1, "retries": retries, "error": str(e)},
                )
            except Exception as e:
                logger.error(
                    "Download error",
                    extra={"attempt": attempt + 1, "retries": retries, "error": str(e)},
                )

            time.sleep(delay)

        logger.error(
            "Failed to download log file after all retries",
            extra={"instance_id": instance_id, "file_name": file_name},
        )
        return False


class RdsLogUploader:
    """RDSログをS3にアップロードするクラス"""

    def __init__(self, destination_bucket: str):
        self.s3_client = boto3.client("s3")
        self.destination_bucket = destination_bucket

    @tracer.capture_method
    def upload_log(
        self, file_path: str, object_key: str, db_instance_id: str, last_written: int
    ) -> bool:
        """
        ログファイルをS3にアップロード

        Args:
            file_path: アップロードするファイルのパス
            object_key: S3オブジェクトキー
            db_instance_id: DBインスタンス識別子
            last_written: 最終更新タイムスタンプ

        Returns:
            bool: アップロード成功時True
        """
        try:
            # メタデータの設定
            metadata = {
                "LastWritten": str(last_written),
                "DbInstanceIdentifier": db_instance_id,
            }

            self.s3_client.upload_file(
                Filename=file_path,
                Bucket=self.destination_bucket,
                Key=object_key,
                ExtraArgs={"Metadata": metadata, "ContentType": "text/plain"},
                Config=boto3.s3.transfer.TransferConfig(
                    multipart_threshold=8 * 1024 * 1024,  # 8MB
                    max_concurrency=10,
                    multipart_chunksize=8 * 1024 * 1024,  # 8MB
                    use_threads=True,
                ),
            )

            logger.info(
                "Successfully uploaded log file to S3",
                extra={
                    "file_path": file_path,
                    "bucket": self.destination_bucket,
                    "object_key": object_key,
                    "size": os.path.getsize(file_path),
                    "metadata": metadata,
                },
            )
            return True

        except Exception as e:
            logger.exception(
                "Failed to upload log file to S3",
                extra={
                    "file_path": file_path,
                    "bucket": self.destination_bucket,
                    "object_key": object_key,
                    "error": str(e),
                },
            )
            return False


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """Lambda関数のハンドラー"""
    try:
        logger.debug("Processing event", extra={"event": event})
        logger.info("event", extra={"event": event})

        destination_bucket = event.get("LogDestinationBucket")
        if not destination_bucket:
            raise ValueError("LogDestinationBucket is required")

        # 一時ファイルの作成
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            # ダウンロード
            downloader = RdsLogDownloader()
            if not downloader.download_log_file(
                event["DbInstanceIdentifier"], event["LogFileName"], temp_path
            ):
                raise Exception("Failed to download log file")

            # アップロード
            uploader = RdsLogUploader(destination_bucket)
            if not uploader.upload_log(
                temp_path,
                event["ObjectKey"],
                event["DbInstanceIdentifier"],
                event["LastWritten"],
            ):
                raise Exception("Failed to upload log file")

            return {
                "statusCode": 200,
                "body": {
                    "message": "Successfully processed log file",
                    "db_instance": event["DbInstanceIdentifier"],
                    "log_file": event["LogFileName"],
                    "object_key": event["ObjectKey"],
                    "last_written": event["LastWritten"],
                },
            }

        finally:
            # 一時ファイルの削除
            if os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        logger.exception("Unexpected error", error=str(e))
        sys.exit(1)
