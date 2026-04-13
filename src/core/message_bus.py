"""
Message Bus — Pub-sub over multiprocessing-safe queues.

Provides decoupled communication between processes/threads.
Publishers and subscribers never need to know about each other.
"""
import multiprocessing as mp
from collections import defaultdict
from typing import Dict, List, Any, Optional
from queue import Full, Empty

from core.logger import Logger


class MessageBus:
    """
    Publish-subscribe message bus using multiprocessing queues.

    Each subscriber gets its own bounded queue. When a subscriber
    is too slow, messages are dropped (not blocked) to prevent
    backpressure from stalling the publisher.

    Usage:
        bus = MessageBus()
        q = bus.subscribe("frame.captured")
        bus.publish("frame.captured", {"slot": 0, "timestamp": 1234.5})
        msg = q.get(timeout=1)
    """

    def __init__(self):
        self.logger = Logger("MessageBus")
        self._subscribers: Dict[str, List[mp.Queue]] = defaultdict(list)
        self._lock = mp.Lock()

    def subscribe(self, topic: str, maxsize: int = 16) -> mp.Queue:
        """
        Subscribe to a topic.

        Args:
            topic: The topic name (e.g. "frame.captured").
            maxsize: Max messages buffered before drops occur.

        Returns:
            A multiprocessing.Queue that receives published messages.
        """
        q = mp.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers[topic].append(q)
        self.logger.debug(f"Subscribed to '{topic}' (maxsize={maxsize})")
        return q

    def publish(self, topic: str, data: dict):
        """
        Publish a message to all subscribers of a topic.

        Non-blocking: if a subscriber's queue is full, the message
        is dropped for that subscriber (others still receive it).
        """
        with self._lock:
            queues = list(self._subscribers.get(topic, []))
        for q in queues:
            try:
                q.put_nowait(data)
            except Full:
                pass  # subscriber too slow — drop

    def drain(self, queue: mp.Queue, max_items: int = 100) -> List[dict]:
        """
        Drain all available messages from a queue (non-blocking).

        Args:
            queue: The subscriber queue to drain.
            max_items: Safety limit to prevent infinite loops.

        Returns:
            List of messages (may be empty).
        """
        messages = []
        for _ in range(max_items):
            try:
                messages.append(queue.get_nowait())
            except Empty:
                break
        return messages

    def get_latest(self, queue: mp.Queue) -> Optional[dict]:
        """
        Get only the most recent message from a queue, discarding older ones.

        Returns None if the queue is empty.
        """
        latest = None
        try:
            while True:
                latest = queue.get_nowait()
        except Empty:
            pass
        return latest

    def close(self):
        """Close all subscriber queues."""
        with self._lock:
            for topic, queues in self._subscribers.items():
                for q in queues:
                    try:
                        q.close()
                        q.join_thread()
                    except Exception:
                        pass
            self._subscribers.clear()
        self.logger.info("Message bus closed")
