import json
import logging
from typing import Any

from confluent_kafka import Producer

from app.settings import settings

logger = logging.getLogger(__name__)


def publish_event(topic: str, payload: dict[str, Any]) -> None:
    try:
        producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
        producer.produce(topic, json.dumps(payload, default=str).encode("utf-8"))
        producer.flush(2)
    except Exception:
        logger.exception("Failed to publish Kafka event to %s", topic)
