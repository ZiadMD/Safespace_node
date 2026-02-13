"""
managers — High-level orchestrators that wire handlers together.

Modules:
    input  — InputManager (camera/video → buffer)
    ai     — AIManager (buffer → inference → callbacks)
    output — OutputManager (display + server event bridge)
"""
