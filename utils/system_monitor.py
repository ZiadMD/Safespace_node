"""
System Monitor - Tracks FPS, CPU, and Memory usage
"""
import psutil
import time
from typing import Dict


class SystemMonitor:
    """Monitor system performance metrics."""
    
    def __init__(self):
        self.frame_count = 0
        self.start_time = time.time()
        self.last_fps_update = time.time()
        self.current_fps = 0.0
        
    def update_frame(self):
        """Call this every time a frame is processed."""
        self.frame_count += 1
        current_time = time.time()
        
        # Update FPS every second
        if current_time - self.last_fps_update >= 1.0:
            self.current_fps = self.frame_count / (current_time - self.last_fps_update)
            self.frame_count = 0
            self.last_fps_update = current_time
    
    def get_metrics(self) -> Dict[str, float]:
        """Get current system metrics."""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        cpu_count = psutil.cpu_count()
        
        return {
            'fps': round(self.current_fps, 1),
            'cpu_percent': round(cpu_percent, 1),
            'memory_used_mb': round(memory.used / (1024 * 1024), 1),
            'memory_percent': round(memory.percent, 1),
            'cpu_cores': cpu_count
        }