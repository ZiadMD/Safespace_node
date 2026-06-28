# Safespace Node — Class Diagrams

UML class diagrams split by subsystem. Each diagram stands alone.

Legend:
- `*--` composition (owner creates and owns the part)
- `o--` aggregation (shared/injected reference, created elsewhere)
- `..>` dependency (transient use / creation)
- `--|>` inheritance

---

## 1. Top-Level Orchestration

**Figure X.5.1.** UML class diagram of the Safespace Node top-level orchestration. Composition (filled diamond) links the `SafespaceNode` orchestrator to the `Config`, `FrameBuffer`, `GPSHandler`, and the five subsystem managers it creates and owns for the lifetime of the node.

```mermaid
classDiagram
    class SafespaceNode {
        +Config config
        +GPSHandler gps
        +FrameBuffer buffer
        +StreamManager stream
        +OutputManager output
        +NetworkManager network
        +InputManager input
        +AIManager ai
        +bool running
        +start()
        +stop()
        -_on_ai_detection(model_name, detections, frame)
        -_on_imx500_detection(model_name, detections, frame)
        -_on_manual_trigger()
    }
    class InputManager
    class AIManager
    class OutputManager
    class NetworkManager
    class StreamManager
    class FrameBuffer
    class GPSHandler
    class Config

    SafespaceNode *-- Config
    SafespaceNode *-- FrameBuffer
    SafespaceNode *-- GPSHandler
    SafespaceNode *-- InputManager
    SafespaceNode *-- AIManager
    SafespaceNode *-- OutputManager
    SafespaceNode *-- NetworkManager
    SafespaceNode *-- StreamManager
```

---

## 2. Input Subsystem (capture)

**Figure X.5.2.** UML class diagram of the input (capture) subsystem. Composition links `InputManager` to its concrete frame source — either a `CameraHandler` or a `VideoHandler` — while aggregation (open diamond) links it to the shared `FrameBuffer`. The buffer produces `TimestampedFrame` records (dependency).

```mermaid
classDiagram
    class InputManager {
        +Config config
        +FrameBuffer buffer
        +Callable on_frame
        +Callable on_imx500_detection
        +source : CameraHandler|VideoHandler
        +start() bool
        +stop()
        -_capture_loop()
        +source_type() str
    }
    class CameraHandler {
        +start() bool
        +read_frame() MatLike
        +get_imx500_detections() dict
        +is_imx500() bool
        +stop()
    }
    class VideoHandler {
        +start() bool
        +read_frame() MatLike
        +fps() float
        +frame_count() int
        +stop()
    }
    class FrameBuffer {
        +write_frame(frame)
        +get_latest() MatLike
        +get_clip(seconds) List~TimestampedFrame~
        +size() int
        +clear()
    }
    class TimestampedFrame {
        +MatLike frame
        +float timestamp
    }

    InputManager o-- FrameBuffer
    InputManager *-- CameraHandler
    InputManager *-- VideoHandler
    FrameBuffer ..> TimestampedFrame : produces
```

---

## 3. AI / Inference Subsystem

**Figure X.5.3.** UML class diagram of the AI/inference subsystem. Composition links `AIManager` to its `ModelLoader` and `ModelDetection` collaborators, and aggregation links it to the shared `FrameBuffer`. Dependency arrows show `ModelLoader` creating and `ModelDetection` consuming `OnnxModel` instances for `.onnx` weights.

```mermaid
classDiagram
    class AIManager {
        +Config config
        +FrameBuffer buffer
        +Callable on_detection
        +Callable on_frame_processed
        -ModelLoader _loader
        -ModelDetection _detector
        +start()
        +stop()
        -_inference_loop()
        +detect_once(model_name, frame) Detections
        +loaded_models() List
    }
    class ModelLoader {
        +load(model_path) Any
        +unload(model_path) bool
        +unload_all()
        +loaded_models() list
    }
    class ModelDetection {
        +detect(...) Detections
        -_detect_yolo(...)
        -_detect_onnx(...)
        -_postprocess_onnx(...)
        -_filter_by_class(...)
    }
    class OnnxModel {
        +str model_path
        +input_shape() Tuple
        +num_classes() int
    }
    class FrameBuffer

    AIManager o-- FrameBuffer
    AIManager *-- ModelLoader
    AIManager *-- ModelDetection
    ModelLoader ..> OnnxModel : creates (.onnx)
    ModelDetection ..> OnnxModel : uses
```

---

## 4. Network Subsystem

**Figure X.5.4.** UML class diagram of the network subsystem. Composition links `NetworkManager` to the `SocketHandler` it owns (Socket.IO + raw WebSocket transport), while aggregation links it to the `GPSHandler` injected after construction for location-tagged heartbeats and accident reports.

```mermaid
classDiagram
    class NetworkManager {
        +Config config
        +Callable on_road_update
        +Callable on_accident_cleared
        -SocketHandler _socket
        -GPSHandler _gps
        +start()
        +stop()
        -_heartbeat_loop()
        +register_node()
        +report_accident(detections, frame)
        -_build_accident_payload(...)
        -_on_command(message)
        -_handle_accident_decision(data)
        +is_connected() bool
    }
    class SocketHandler {
        +emit_accident(payload) Dict
        +connect()
        +disconnect()
        +is_sio_connected() bool
        +is_ws_connected() bool
    }
    class GPSHandler {
        +start()
        +stop()
        +get_location() Dict
        +has_fix() bool
        +is_enabled() bool
    }

    NetworkManager *-- SocketHandler
    NetworkManager o-- GPSHandler
```

---

## 5. Stream Subsystem (RTSP)

**Figure X.5.5.** UML class diagram of the RTSP stream subsystem. Composition links `StreamManager` (which supervises the MediaMTX subprocess) to the `StreamHandler` it owns, and aggregation links the handler to the shared `FrameBuffer` it reads from to feed the `ffmpeg` publisher.

```mermaid
classDiagram
    class StreamManager {
        +Config config
        -StreamHandler _handler
        +start()
        +stop()
        -_start_mediamtx() bool
        -_stop_mediamtx()
        +is_streaming() bool
        +rtsp_url() str
    }
    class StreamHandler {
        +Config config
        +FrameBuffer buffer
        +start()
        +stop()
        -_stream_loop()
        -_build_ffmpeg_cmd()
        -_start_ffmpeg()
        +rtsp_url() str
    }
    class FrameBuffer

    StreamManager *-- StreamHandler
    StreamHandler o-- FrameBuffer
```

---

## 6. Display / GUI Subsystem

**Figure X.5.6.** UML class diagram of the display/GUI subsystem. Composition links `OutputManager` → `DisplayHandler` → `MainWindow`, which in turn owns the `LaneWidget`, `SpeedWidget`, `VideoFeedWidget`, and `SystemMonitorWidget`. A generalisation tree shows `MainWindow` specialising `QMainWindow` and each widget specialising `QFrame` (PyQt6).

```mermaid
classDiagram
    class OutputManager {
        +DisplayHandler display
        +push_input_frame(frame)
        +push_ai_frame(frame)
        +on_accident_detected(model_name, detections, frame)
        +apply_road_update(data)
        +update_lane(lane_index, status)
        +update_speed(limit)
        +trigger_accident_alert()
        +clear_accident()
    }
    class DisplayHandler {
        +start()
        +update_lane_status(lane_index, status)
        +update_speed_limit(limit)
        +set_accident_alert(active)
        +push_input_frame(frame)
        +push_ai_frame(frame)
        +reset_display()
    }
    class MainWindow {
        +update_lane(lane_index, status)
        +update_speed(limit)
        +set_accident_alert(active)
        +push_input_frame(frame)
        +update_gps_status(has_fix)
        +keyPressEvent(event)
    }
    class LaneWidget {
        +set_status(status)
    }
    class SpeedWidget {
        +set_speed(limit)
        +set_alert_mode(active)
    }
    class VideoFeedWidget {
        +push_frame(frame)
    }
    class SystemMonitorWidget
    class QMainWindow
    class QFrame

    OutputManager *-- DisplayHandler
    DisplayHandler *-- MainWindow
    MainWindow --|> QMainWindow
    MainWindow *-- LaneWidget
    MainWindow *-- SpeedWidget
    MainWindow *-- VideoFeedWidget
    MainWindow *-- SystemMonitorWidget
    LaneWidget --|> QFrame
    SpeedWidget --|> QFrame
    VideoFeedWidget --|> QFrame
    SystemMonitorWidget --|> QFrame
```

---

## 7. Utilities & Error Hierarchy

**Figure X.5.7.** UML class diagram of the shared utilities and error hierarchy. A generalisation tree models the `SafespaceError` hierarchy (`NetworkError`, `ConfigError`, `DisplayError`, `GPSError`), tracked by `FailureManager` (dependency). `Config` and `Logger` are the cross-cutting configuration and logging utilities used throughout the node.

```mermaid
classDiagram
    class Config {
        +get(key, default) Any
        +get_int(key, default) int
        +get_float(key, default) float
        +get_bool(key, default) bool
        +save_to_file(path)
    }
    class Logger {
        +setup(settings)$
        +info(message)
        +warning(message)
        +error(message)
        +debug(message)
        +critical(message)
    }
    class FailureManager {
        +int threshold
        +int window_seconds
        +record_failure(error)
        +is_threshold_exceeded(error_type) bool
        +clear()
    }
    class SafespaceError {
        +str message
        +bool critical
    }
    class NetworkError
    class ConfigError
    class DisplayError
    class GPSError

    NetworkError --|> SafespaceError
    ConfigError --|> SafespaceError
    DisplayError --|> SafespaceError
    GPSError --|> SafespaceError
    FailureManager ..> SafespaceError : tracks
```
