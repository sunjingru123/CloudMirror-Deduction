"""应用配置。

配置项通过环境变量或 `.env` 文件读取，默认值适用于本地开发。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置对象。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 基本信息
    PROJECT_NAME: str = "云镜推演"
    PROJECT_NAME_EN: str = "CloudMirror Deduction"
    DESCRIPTION: str = "面向云原生业务系统的故障传播分析与恢复策略优化平台"
    VERSION: str = "0.1.0"
    DEBUG: bool = True

    # 接口前缀
    API_PREFIX: str = "/api"

    # 数据库（默认使用 SQLite，文件位于 backend 运行目录）
    DATABASE_URL: str = "sqlite:///./cloudmirror.db"

    # 允许跨域的前端地址（逗号分隔）
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """返回去除空白后的跨域来源列表。"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
