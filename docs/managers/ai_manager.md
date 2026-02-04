# AI Manager

The AI Manager orchestrates the AI detection pipeline, managing model loading, frame processing, and detection callbacks.

## Overview

```mermaid
classDiagram
    class AIManager {
        -config: Config
        -io_manager: IOManager
        -logger: Logger
        -on_detection: Callable
        -model_loader: ModelLoader
        -detection_handler: ModelDetectionHandler
        -visuals_handler: DetectionVisualsHandler
        -models: Dict~str, Dict~
        +__init__(config, io_manager, on_detection)
        +load_model(model_name) Any
        +unload_model(model_name) bool
        +get_model(model_name) Any
        +detect(model_name, frame) sv.Detections
        +detect_and_visualize(model_name, frame) tuple
        +process_latest() Dict
        -_load_enabled_models()
        -_process_frame(frame)
    }
    
    AIManager --> ModelLoader
    AIManager --> ModelDetectionHandler
    AIManager --> DetectionVisualsHandler
    AIManager --> IOManager
    AIManager --> Logger
```

## Purpose

The AI Manager provides:

1. **Model Lifecycle** - Load, cache, and unload detection models
2. **Automatic Processing** - Push-based frame processing via callbacks
3. **Manual Processing** - Pull-based detection on demand
4. **Detection Events** - Notify when objects are detected
5. **Visualization** - Annotate frames with detection results

## Architecture

```mermaid
flowchart TD
    subgraph "AI Manager"
        AIM[AI Manager]
        
        subgraph "Handlers"
            ML[Model Loader]
            DET[Detection Handler]
            VIS[Visuals Handler]
        end
        
        subgraph "Model Cache"
            M1["accident_detection<br/>{model, confidence, classes}"]
            M2["vehicle_detection<br/>{model, confidence, classes}"]
        end
    end
    
    subgraph "External"
        IOM[IO Manager]
        MAIN[SafespaceNode]
        CONFIG[ai.json]
    end
    
    AIM --> ML
    AIM --> DET
    AIM --> VIS
    
    AIM --> M1
    AIM --> M2
    
    IOM --> |frame callback| AIM
    AIM --> |on_detection| MAIN
    CONFIG --> |model configs| AIM
```

## Detection Modes

### Push Mode (Automatic)

```mermaid
sequenceDiagram
    participant IOManager
    participant AIManager
    participant Models
    participant SafespaceNode
    
    IOManager->>AIManager: _process_frame(frame)
    
    loop For each loaded model
        AIManager->>Models: detect(frame)
        Models-->>AIManager: detections
        
        alt Detections found
            AIManager->>SafespaceNode: on_detection(model_name, detections, frame)
        end
    end
```

### Pull Mode (On Demand)

```mermaid
sequenceDiagram
    participant Client
    participant AIManager
    participant IOManager
    participant Models
    
    Client->>AIManager: process_latest()
    AIManager->>IOManager: get_latest_frame()
    IOManager-->>AIManager: frame
    
    loop For each model
        AIManager->>Models: detect(frame)
        Models-->>AIManager: detections
    end
    
    AIManager-->>Client: {model_name: detections}
```

## Configuration

### ai.json Structure

```json
{
  "ai": {
    "models": {
      "accident_detection": {
        "enabled": true,
        "path": "AI Layer/Models/Car Accident.pt",
        "confidence": 0.5,
        "classes": ["accident"]
      },
      "vehicle_detection": {
        "enabled": false,
        "path": "AI Layer/Models/Vehicle.pt",
        "confidence": 0.6,
        "classes": ["car", "truck", "bus"]
      }
    }
  }
}
```

### Configuration Fields

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Whether to load model on startup |
| `path` | string | Path to `.pt` model file |
| `confidence` | float | Detection threshold (0.0 - 1.0) |
| `classes` | array | Class names for labeling |

## API Reference

### Constructor

```python
def __init__(self, config: Config, io_manager: IOManager, 
             on_detection: Optional[Callable[[str, sv.Detections, MatLike], None]] = None)
```

**Parameters:**
- `config`: Configuration object
- `io_manager`: IO Manager for frame access
- `on_detection`: Callback for detections `(model_name, detections, frame)`

### Methods

#### `load_model(model_name: str) -> Optional[Any]`

Loads a model by name from configuration.

```python
model = ai_manager.load_model("accident_detection")
```

**Returns:** Loaded model or `None` if failed

---

#### `unload_model(model_name: str) -> bool`

Unloads a model from cache.

```python
ai_manager.unload_model("accident_detection")
```

**Returns:** `True` if model was unloaded

---

#### `get_model(model_name: str) -> Optional[Any]`

Retrieves a loaded model by name.

```python
model = ai_manager.get_model("accident_detection")
```

---

#### `detect(model_name: str, frame: MatLike) -> Optional[sv.Detections]`

Runs detection on a frame with a specific model.

```python
detections = ai_manager.detect("accident_detection", frame)
if detections and len(detections) > 0:
    print(f"Found {len(detections)} objects")
```

---

#### `detect_and_visualize(model_name: str, frame: MatLike) -> tuple`

Runs detection and returns annotated frame.

```python
detections, annotated_frame = ai_manager.detect_and_visualize("accident_detection", frame)
cv2.imshow("Detections", annotated_frame)
```

**Returns:** `(detections, annotated_frame)`

---

#### `process_latest() -> Dict[str, sv.Detections]`

Processes the latest frame with all loaded models.

```python
results = ai_manager.process_latest()
for model_name, detections in results.items():
    print(f"{model_name}: {len(detections)} detections")
```

**Returns:** Dictionary mapping model names to detections

## Model Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Unloaded
    
    Unloaded --> Loading: load_model()
    Loading --> Loaded: success
    Loading --> Unloaded: failure
    
    Loaded --> Processing: _process_frame()
    Processing --> Loaded: complete
    
    Loaded --> Unloading: unload_model()
    Unloading --> Unloaded: complete
```

## Model Cache Structure

```python
self.models = {
    "accident_detection": {
        "model": YOLO(...),      # Loaded model
        "confidence": 0.5,        # Detection threshold
        "classes": ["accident"]   # Class names
    },
    "vehicle_detection": {
        "model": YOLO(...),
        "confidence": 0.6,
        "classes": ["car", "truck", "bus"]
    }
}
```

## Frame Processing Flow

```mermaid
flowchart TD
    FRAME[New Frame from IO Manager]
    LOOP[For Each Model]
    GET[Get Model Data]
    DETECT[Run Detection]
    CHECK{Detections > 0?}
    CALLBACK[Invoke on_detection]
    NEXT[Next Model]
    DONE[Processing Complete]
    
    FRAME --> LOOP
    LOOP --> GET
    GET --> DETECT
    DETECT --> CHECK
    CHECK --> |Yes| CALLBACK
    CHECK --> |No| NEXT
    CALLBACK --> NEXT
    NEXT --> |More Models| LOOP
    NEXT --> |Done| DONE
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Model not found | Log error, return `None` |
| Invalid config | Log error, skip model |
| Detection error | Exception propagated |
| Frame callback error | Logged in IO Manager |

## Usage Example

```python
from Managers.AI_Manger import AIManager
from Managers.IO_Manager import IOManager
from utils.config import Config

def on_detection(model_name, detections, frame):
    print(f"[{model_name}] Detected {len(detections)} objects!")
    
    if 'accident' in model_name:
        # Handle accident detection
        save_snapshot(frame)
        report_accident()

# Initialize
config = Config()
io_manager = IOManager(config)
ai_manager = AIManager(config, io_manager, on_detection=on_detection)

# Models are auto-loaded based on config
print(f"Loaded models: {list(ai_manager.models.keys())}")

# Manual detection (optional)
frame = io_manager.get_latest_frame()
if frame is not None:
    detections = ai_manager.detect("accident_detection", frame)
```

## Integration with SafespaceNode

```mermaid
flowchart TD
    subgraph "SafespaceNode"
        INIT[Initialize]
        CB[_on_ai_detection]
        SAVE[Save Snapshot]
        REPORT[Report Accident]
    end
    
    subgraph "AI Manager"
        AIM[AIManager]
        PROC[_process_frame]
    end
    
    subgraph "IO Manager"
        IOM[IOManager]
        FRAMES[Frame Stream]
    end
    
    INIT --> |create| AIM
    INIT --> |pass callback| AIM
    
    FRAMES --> |callback| PROC
    PROC --> |on_detection| CB
    CB --> SAVE
    SAVE --> REPORT
```

## Performance Considerations

### Multiple Models

Running multiple models increases processing time:

| Models | Typical Frame Time |
|--------|-------------------|
| 1 model | 30-50 ms |
| 2 models | 60-100 ms |
| 3 models | 90-150 ms |

### Optimization Tips

1. **Disable unused models** in config
2. **Use smaller models** (YOLOv8n vs YOLOv8x)
3. **Adjust confidence threshold** to reduce post-processing
4. **Use GPU acceleration** when available

## Related Components

- [Model Loader Handler](../handlers/model_loader_handler.md) - Model loading
- [Model Detection Handler](../handlers/model_detection_handler.md) - Inference
- [Detection Visuals Handler](../handlers/detection_visuals_handler.md) - Visualization
- [IO Manager](io_manager.md) - Frame source
- [SafespaceNode](../core/main.md) - Detection consumer
