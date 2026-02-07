"""
Pipeline stages for the Safespace Node.

The video processing pipeline is modeled as independent stages
connected by bounded queues:

    CaptureStage → [frame_queue] → InferenceStage → [detection_queue] → DecisionStage

Each stage runs in its own thread. Bounded queues provide natural
backpressure — if inference is slow, old frames are dropped (not queued).
"""
from .capture import CaptureStage
from .inference import InferenceStage
from .decision import DecisionStage

__all__ = ["CaptureStage", "InferenceStage", "DecisionStage"]
