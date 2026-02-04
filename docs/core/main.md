# SafespaceNode (Main Orchestrator)

The SafespaceNode class is the main entry point and orchestrator for the Safespace road safety monitoring system. It coordinates all managers and handles the application lifecycle.

## Overview

```mermaid
classDiagram
    class SafespaceNode {
        -config: Config
        -offline: bool
        -enable_ai: bool
        -logger: Logger
        -network: NetworkManager
        -io: IOManager
        -ai: AIManager
        -running: bool
        -awaiting_confirmation: bool
        +__init__(video_path, offline, enable_ai)
        +start()
        +stop()
        -_setup_signals()
        -_on_manual_accident_report()
        -_on_ai_detection(model_name, detections, frame)
        -_save_ai_detection_snapshot(frame)
        -_on_central_unit_instruction(data)
    }
    
    SafespaceNode --> Config
    SafespaceNode --> Logger
    SafespaceNode --> NetworkManager
    SafespaceNode --> IOManager
    SafespaceNode --> AIManager
```

## Purpose

The SafespaceNode orchestrator provides:

1. **Initialization** - Load config, setup logging, create managers
2. **Lifecycle Management** - Start/stop all services
3. **Event Routing** - Connect managers via callbacks
4. **Accident Handling** - Process manual and AI-detected incidents
5. **Signal Handling** - Graceful shutdown on SIGINT/SIGTERM

## Architecture

```mermaid
flowchart TD
    subgraph "SafespaceNode"
        MAIN[SafespaceNode<br/>Orchestrator]
        
        subgraph "Managers"
            NET[Network Manager]
            IO[IO Manager]
            AI[AI Manager]
        end
        
        subgraph "Callbacks"
            CB1[_on_manual_accident_report]
            CB2[_on_ai_detection]
            CB3[_on_central_unit_instruction]
        end
    end
    
    subgraph "External"
        CONFIG[Config Files]
        CAMERA[Camera/Video]
        SERVER[Central Unit]
        USER[User Input]
    end
    
    CONFIG --> MAIN
    MAIN --> NET
    MAIN --> IO
    MAIN --> AI
    
    IO --> |manual trigger| CB1
    AI --> |detection| CB2
    NET --> |instruction| CB3
    
    CB1 --> NET
    CB2 --> NET
    CB3 --> IO
    
    CAMERA --> IO
    USER --> IO
    NET <--> SERVER
```

## Command Line Interface

```bash
python main.py [OPTIONS]
```

### Arguments

| Argument | Short | Type | Description |
|----------|-------|------|-------------|
| `--video` | `-v` | string | Path to video file for testing |
| `--offline` | `-o` | flag | Run without network connection |
| `--no-ai` | - | flag | Disable AI detection |

### Examples

```bash
# Standard mode (camera + network + AI)
python main.py

# Video test mode
python main.py --video /path/to/test.mp4

# Offline mode (no network)
python main.py --offline

# Without AI (manual detection only)
python main.py --no-ai

# Combined flags
python main.py -v test.mp4 -o --no-ai
```

## Initialization Flow

```mermaid
sequenceDiagram
    participant CLI
    participant Main as SafespaceNode
    participant Config
    participant Logger
    participant Network as NetworkManager
    participant IO as IOManager
    participant AI as AIManager
    
    CLI->>Main: __init__(video_path, offline, enable_ai)
    Main->>Config: Load configuration
    Main->>Logger: Setup logging
    
    Main->>Network: Create(config, callback)
    Main->>IO: Create(config, callback, video_path)
    
    alt AI Enabled
        Main->>AI: Create(config, io, callback)
        AI->>IO: Register frame callback
    end
    
    Main->>Main: Setup signal handlers
```

## Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Initialized: __init__()
    
    Initialized --> Starting: start()
    
    Starting --> NetworkConnecting: if not offline
    Starting --> SkipNetwork: if offline
    
    NetworkConnecting --> NetworkFailed: connection failed
    NetworkConnecting --> Running: connected
    SkipNetwork --> Running: skip
    NetworkFailed --> Running: continue anyway
    
    Running --> IOBlocking: io.start()
    
    IOBlocking --> Stopping: window closed / signal
    
    Stopping --> Stopped: stop()
    Stopped --> [*]
```

## API Reference

### Constructor

```python
def __init__(self, video_path: str = None, offline: bool = False, enable_ai: bool = True)
```

**Parameters:**
- `video_path`: Optional path to video file (replaces camera)
- `offline`: Skip network connection if `True`
- `enable_ai`: Initialize AI detection if `True`

### Methods

#### `start()`

Starts all node services.

```python
node = SafespaceNode(video_path="test.mp4")
node.start()  # Blocks until stopped
```

**Sequence:**
1. Connect to network (unless offline)
2. Set `running = True`
3. Start IO manager (blocks on Qt event loop)
4. Stop services on exit

---

#### `stop()`

Cleanly shuts down all services.

```python
node.stop()
```

**Sequence:**
1. Set `running = False`
2. Stop network manager
3. Stop IO manager
4. Log shutdown complete

## Event Handling

### Manual Accident Report

```mermaid
sequenceDiagram
    participant User
    participant Display as DisplayHandler
    participant IO as IOManager
    participant Main as SafespaceNode
    participant Network as NetworkManager
    participant Server as Central Unit
    
    User->>Display: Press Spacebar
    Display->>Main: _on_manual_accident_report()
    
    alt Not awaiting confirmation
        Main->>Main: awaiting_confirmation = True
        Main->>IO: get_accident_snapshot()
        IO-->>Main: snapshot_path
        Main->>Network: report_accident(lane, media)
        Network->>Server: HTTP POST
    else Already awaiting
        Main->>Main: Log warning, ignore
    end
```

### AI Detection

```mermaid
sequenceDiagram
    participant Camera
    participant IO as IOManager
    participant AI as AIManager
    participant Main as SafespaceNode
    participant Network as NetworkManager
    
    Camera->>IO: New frame
    IO->>AI: frame_callback(frame)
    AI->>AI: Run detection
    
    alt Objects detected
        AI->>Main: _on_ai_detection(model, detections, frame)
        
        alt Accident model & not awaiting
            Main->>Main: Save snapshot
            Main->>Main: awaiting_confirmation = True
            Main->>Network: report_accident(lane, media, ai_detected=True)
        end
    end
```

### Central Unit Instruction

```mermaid
sequenceDiagram
    participant Server as Central Unit
    participant Network as NetworkManager
    participant Main as SafespaceNode
    participant IO as IOManager
    participant Display as DisplayHandler
    
    Server->>Network: WebSocket event
    Network->>Main: _on_central_unit_instruction(data)
    
    Main->>Main: awaiting_confirmation = False
    
    alt isAccident == False
        Main->>IO: reset_display()
    else isAccident == True
        Main->>IO: toggle_alert(True)
    end
    
    alt speedLimit present
        Main->>IO: update_speed(limit)
    end
    
    alt laneStates present
        loop Each lane
            Main->>IO: update_status(index, status)
        end
    end
```

## State Management

### Awaiting Confirmation

The `awaiting_confirmation` flag prevents duplicate reports:

```mermaid
stateDiagram-v2
    [*] --> Idle
    
    Idle --> Awaiting: Report sent (manual or AI)
    
    Awaiting --> Awaiting: Ignore new reports
    Awaiting --> Idle: Instruction received
    
    Idle --> Idle: No action needed
```

## Signal Handling

```python
def _setup_signals(self):
    def handler(sig, frame):
        self.logger.info("Shutdown signal received")
        self.stop()
    signal.signal(signal.SIGINT, handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, handler)  # kill command
```

## Configuration Requirements

The node requires these configuration files:

| File | Required Keys |
|------|---------------|
| `node.json` | `node.id`, `node.location`, `node.lanes` |
| `network.json` | `network.server_url` |
| `camera.json` | `camera.index`, `camera.fps` |
| `logging.json` | `logging.level` |
| `ai.json` | `ai.models` (if AI enabled) |

## Usage Example

```python
import sys
import os

# Add safespace to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import SafespaceNode

# Create node
node = SafespaceNode(
    video_path="/path/to/test.mp4",  # Optional
    offline=False,                    # Connect to server
    enable_ai=True                    # Enable AI detection
)

# Start (blocks)
node.start()

# After window closes or signal received:
# - Network disconnected
# - Camera/video stopped
# - Logs written
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Network connection fails | Continue in offline mode |
| Camera fails to start | Continue in display-only mode |
| AI model fails to load | Continue without AI |
| IO runtime error | Log error, trigger stop |
| Signal received | Graceful shutdown |

## Complete Data Flow

```mermaid
flowchart TD
    subgraph "Input"
        CAM[Camera/Video]
        USER[User Spacebar]
        SERVER[Central Unit]
    end
    
    subgraph "SafespaceNode"
        MAIN[Orchestrator]
        
        subgraph "Processing"
            IOM[IO Manager]
            AIM[AI Manager]
            NETM[Network Manager]
        end
        
        subgraph "Callbacks"
            MANUAL[Manual Report]
            AIDET[AI Detection]
            INST[Instruction]
        end
    end
    
    subgraph "Output"
        DISPLAY[Display UI]
        UPLOAD[Server Upload]
        SNAPSHOT[Snapshot Files]
    end
    
    CAM --> IOM
    USER --> IOM
    SERVER --> NETM
    
    IOM --> AIM
    IOM --> MANUAL
    AIM --> AIDET
    NETM --> INST
    
    MANUAL --> NETM
    AIDET --> NETM
    AIDET --> SNAPSHOT
    INST --> IOM
    
    NETM --> UPLOAD
    IOM --> DISPLAY
```

## Related Components

- [IO Manager](../managers/io_manager.md) - Input/Output coordination
- [AI Manager](../managers/ai_manager.md) - Detection pipeline
- [Network Manager](../managers/network_manager.md) - Server communication
- [Config](../utilities/config.md) - Configuration loading
- [Logger](../utilities/logger.md) - Logging setup
