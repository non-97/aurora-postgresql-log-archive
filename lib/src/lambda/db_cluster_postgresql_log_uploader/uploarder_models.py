from dataclasses import dataclass


@dataclass(frozen=True)
class LogFileConfig:
    """イベントから設定値を取得するデータクラス"""

    db_instance_identifier: str
    log_destination_bucket: str
    last_written: int
    log_file_name: str
    object_key: str

    def __post_init__(self) -> None:
        """初期化後のバリデーション"""
        if not self.db_instance_identifier:
            raise ValueError("DbClusterIdentifier is required")
        if not self.log_destination_bucket:
            raise ValueError("LogDestinationBucket is required")
        if not self.last_written:
            raise ValueError("LastWritten is required")
        if not self.log_file_name:
            raise ValueError("LogFileName is required")
        if not self.object_key:
            raise ValueError("ObjectKey is required")
