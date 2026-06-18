with open("src/main.py", "r") as f:
    content = f.read()

old = 'from managers.network import NetworkManager'
new = 'from managers.network import NetworkManager\nfrom handlers.gps_handler import GPSHandler'
if old in content:
    content = content.replace(old, new)
    print("Edit 1 OK")
else:
    print("Edit 1 FAILED")

old = '        # 2. Shared Frame Buffer\n        self.buffer = FrameBuffer(self.config)'
new = '        # 2. GPS Handler\n        self.gps = GPSHandler(self.config)\n        self.gps.start()\n\n        # 3. Shared Frame Buffer\n        self.buffer = FrameBuffer(self.config)'
if old in content:
    content = content.replace(old, new)
    print("Edit 2 OK")
else:
    print("Edit 2 FAILED")

old = '        # 5. Input Manager (camera or video \u2192 buffer)'
new = '        # Attach GPS to network manager\n        if self.network:\n            self.network.set_gps_handler(self.gps)\n\n        # 5. Input Manager (camera or video \u2192 buffer)'
if old in content:
    content = content.replace(old, new)
    print("Edit 3 OK")
else:
    print("Edit 3 FAILED")

old = '        if self.ai:\n            self.ai.stop()\n        if self.network:\n            self.network.stop()\n        self.input.stop()'
new = '        if self.ai:\n            self.ai.stop()\n        if self.network:\n            self.network.stop()\n        self.input.stop()\n        if self.gps:\n            self.gps.stop()'
if old in content:
    content = content.replace(old, new)
    print("Edit 4 OK")
else:
    print("Edit 4 FAILED")

with open("src/main.py", "w") as f:
    f.write(content)  
