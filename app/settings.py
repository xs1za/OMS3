from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "OMS3"
    root_path: str = ""
    kafka_bootstrap_servers: str = "kafka.oms.svc.cluster.local:9092"


settings = Settings()
