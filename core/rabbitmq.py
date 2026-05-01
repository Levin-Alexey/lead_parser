from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

import pika


@dataclass
class RabbitMQClient:
	amqp_url: str

	def __post_init__(self) -> None:
		self._connection: pika.BlockingConnection | None = None
		self._channel: pika.adapters.blocking_connection.BlockingChannel | None = None

	def connect(self) -> None:
		params = pika.URLParameters(self.amqp_url)
		params.heartbeat = 30
		params.blocked_connection_timeout = 30

		self._connection = pika.BlockingConnection(params)
		self._channel = self._connection.channel()

	@property
	def channel(self) -> pika.adapters.blocking_connection.BlockingChannel:
		if self._channel is None:
			raise RuntimeError("RabbitMQ channel is not initialized. Call connect() first.")
		return self._channel

	def publish_json(self, queue_name: str, payload: dict) -> None:
		body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
		self.channel.queue_declare(queue=queue_name, durable=True)
		self.channel.basic_publish(
			exchange="",
			routing_key=queue_name,
			body=body,
			properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
		)

	def consume_json(self, queue_name: str, callback: Callable[[dict], bool]) -> None:
		self.channel.queue_declare(queue=queue_name, durable=True)
		self.channel.basic_qos(prefetch_count=1)

		def _handle(ch, method, _properties, body: bytes) -> None:
			try:
				message = json.loads(body.decode("utf-8"))
			except json.JSONDecodeError:
				ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
				return

			is_ok = callback(message)
			if is_ok:
				ch.basic_ack(delivery_tag=method.delivery_tag)
				return

			# Requeue transient failures so worker can retry.
			ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

		self.channel.basic_consume(queue=queue_name, on_message_callback=_handle)
		self.channel.start_consuming()

	def close(self) -> None:
		if self._connection and not self._connection.is_closed:
			self._connection.close()
