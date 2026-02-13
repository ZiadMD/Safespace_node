"""
handlers — Low-level I/O and processing components.

Modules:
    camera          — CameraHandler (native / IMX500)
    video           — VideoHandler (file playback)
    frame_buffer    — FrameBuffer (thread-safe ring buffer)
    model_loader    — ModelLoader (YOLO .pt loader)
    model_detection — ModelDetection (inference + filtering)
    display/        — DisplayHandler (PyQt6 dashboard)
"""
