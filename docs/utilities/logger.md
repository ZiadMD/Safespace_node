# Logger Utility

The Logger utility provides enhanced logging capabilities with console and rotating file output for the Safespace Node application.

## Overview

```mermaid
classDiagram
    class Logger {
        -logger: logging.Logger
        -_configured: bool$
        +setup(settings: dict)$
        +__init__(name: str)
        +info(message: str)
        +warning(message: str)
        +error(message: str)
        +debug(message: str)
        +critical(message: str)
    }
    
    Logger --> "logging.Logger"
    Logger --> "RotatingFileHandler"
    Logger --> "StreamHandler"
```

## Purpose

The Logger utility provides:

1. **Console Output** - Colorful, formatted terminal logging
2. **File Rotation** - Automatic log file rotation when size limit reached
3. **Named Loggers** - Component-specific logging namespaces
4. **Configurable Levels** - DEBUG, INFO, WARNING, ERROR, CRITICAL
5. **Singleton Setup** - Global configuration applied once

## Architecture

```mermaid
flowchart TD
    subgraph "Logger System"
        SETUP[Logger.setup]
        ROOT[Root Logger]
        
        subgraph "Handlers"
            CONSOLE[StreamHandler<br/>stdout]
            FILE[RotatingFileHandler<br/>safespace.log]
        end
        
        subgraph "Formatters"
            FMT["[timestamp] [level] [name] message"]
        end
    end
    
    subgraph "Logger Instances"
        L1[Logger 'SafespaceNode']
        L2[Logger 'IOManager']
        L3[Logger 'NetworkManager']
        L4[Logger 'AIManager']
    end
    
    SETUP --> ROOT
    ROOT --> CONSOLE
    ROOT --> FILE
    CONSOLE --> FMT
    FILE --> FMT
    
    L1 --> ROOT
    L2 --> ROOT
    L3 --> ROOT
    L4 --> ROOT
```

## Configuration

### logging.json Structure

```json
{
  "logging": {
    "level": "INFO",
    "rotation": "5MB",
    "backup_count": 5
  }
}
```

### Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `level` | string | "INFO" | Minimum log level |
| `rotation` | string | "5MB" | Max file size before rotation |
| `backup_count` | int | 5 | Number of backup files to keep |

### Log Levels

| Level | Value | Description |
|-------|-------|-------------|
| DEBUG | 10 | Detailed debugging information |
| INFO | 20 | General operational messages |
| WARNING | 30 | Warning conditions |
| ERROR | 40 | Error conditions |
| CRITICAL | 50 | Critical failures |

## API Reference

### Class Methods

#### `Logger.setup(settings: dict)`

Configures global logging (called once at startup).

```python
Logger.setup({
    'level': 'DEBUG',
    'rotation': '10MB',
    'backup_count': 3
})
```

**Parameters:**
- `settings`: Dictionary with logging configuration

### Instance Methods

#### Constructor

```python
def __init__(self, name: str = "Safespace")
```

Creates a named logger instance.

```python
logger = Logger("MyComponent")
```

---

#### Logging Methods

```python
logger.debug("Detailed debug info")
logger.info("Normal operation message")
logger.warning("Warning condition detected")
logger.error("Error occurred")
logger.critical("Critical failure!")
```

## Log Format

```
[2026-02-05 14:30:45] [INFO] [SafespaceNode] Initializing Safespace Node...
```

| Component | Description |
|-----------|-------------|
| `[2026-02-05 14:30:45]` | Timestamp |
| `[INFO]` | Log level |
| `[SafespaceNode]` | Logger name |
| `Initializing...` | Message |

## File Rotation

```mermaid
flowchart TD
    WRITE[Write Log Entry]
    CHECK{File Size > Max?}
    CONTINUE[Continue Writing]
    ROTATE[Rotate Files]
    
    WRITE --> CHECK
    CHECK --> |No| CONTINUE
    CHECK --> |Yes| ROTATE
    
    subgraph "Rotation Process"
        R1[safespace.log → safespace.log.1]
        R2[safespace.log.1 → safespace.log.2]
        R3[safespace.log.2 → safespace.log.3]
        RN[Delete oldest if > backup_count]
        NEW[Create new safespace.log]
    end
    
    ROTATE --> R1
    R1 --> R2
    R2 --> R3
    R3 --> RN
    RN --> NEW
    NEW --> CONTINUE
```

### Rotation Size Formats

| Format | Size |
|--------|------|
| `"5MB"` | 5 × 1024 × 1024 = 5,242,880 bytes |
| `"10MB"` | 10 × 1024 × 1024 = 10,485,760 bytes |
| `"500KB"` | 500 × 1024 = 512,000 bytes |

## Log Files Location

```
safespace/logs/
├── safespace.log      # Current log file
├── safespace.log.1    # Previous log
├── safespace.log.2    # Older log
├── safespace.log.3    # Even older
└── ...
```

## Setup Flow

```mermaid
sequenceDiagram
    participant Main as main.py
    participant Logger
    participant Root as Root Logger
    participant Console as StreamHandler
    participant File as FileHandler
    
    Main->>Logger: setup(settings)
    
    alt Not configured yet
        Logger->>Root: setLevel(level)
        Logger->>Console: Create StreamHandler
        Logger->>Console: Set formatter
        Logger->>Root: addHandler(console)
        Logger->>File: Create RotatingFileHandler
        Logger->>File: Set formatter
        Logger->>Root: addHandler(file)
        Logger->>Logger: _configured = True
    else Already configured
        Logger-->>Main: Return (no-op)
    end
```

## Usage Example

```python
from utils.logger import Logger

# 1. Global setup (once, typically in main.py)
Logger.setup({
    'level': 'DEBUG',
    'rotation': '5MB',
    'backup_count': 5
})

# 2. Create logger instances
logger = Logger("MyComponent")

# 3. Log messages
logger.debug("Starting processing...")
logger.info("Connected to server")
logger.warning("Retrying connection...")
logger.error("Failed to connect after 3 retries")
logger.critical("System cannot continue!")
```

## Output Examples

### Console Output
```
[2026-02-05 14:30:45] [INFO] [SafespaceNode] Initializing Safespace Node...
[2026-02-05 14:30:45] [INFO] [IOManager] Starting IO components...
[2026-02-05 14:30:46] [INFO] [NetworkManager] Connecting to Central Unit...
[2026-02-05 14:30:46] [WARNING] [CameraHandler] Captured empty frame, retrying...
[2026-02-05 14:30:47] [ERROR] [AIManager] Failed to load model: invalid path
```

### File Output
Same format, written to `safespace/logs/safespace.log`

## Integration Pattern

```mermaid
flowchart TD
    subgraph "Startup"
        MAIN[main.py]
        CONFIG[Config]
        SETUP[Logger.setup]
    end
    
    subgraph "Components"
        L1[Logger 'SafespaceNode']
        L2[Logger 'IOManager']
        L3[Logger 'NetworkManager']
        L4[Logger 'AIManager']
        L5[Logger 'CameraHandler']
    end
    
    MAIN --> CONFIG
    CONFIG --> |logging settings| SETUP
    SETUP --> |configures root| L1
    SETUP --> |configures root| L2
    SETUP --> |configures root| L3
    SETUP --> |configures root| L4
    SETUP --> |configures root| L5
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Invalid level | Falls back to INFO |
| Log dir not writable | File handler skipped |
| Invalid rotation format | Uses default 5MB |
| Setup called twice | Second call is ignored |

## Best Practices

1. **Call setup() once** at application startup
2. **Use descriptive names** for logger instances
3. **Choose appropriate levels**:
   - `debug`: Development details
   - `info`: Normal operations
   - `warning`: Recoverable issues
   - `error`: Failures that need attention
   - `critical`: System-breaking failures

## Related Components

- [Config](config.md) - Provides logging settings
- [All Components](../) - Logger consumers
