#pragma once

#include <memory>
#include <thread>
#include <atomic>

class CameraHandler;
class VideoHandler;
class FrameBuffer;

class InputManager {
public:
    InputManager(std::shared_ptr<FrameBuffer> buffer);
    ~InputManager();

    void start();
    void stop();

private:
    void loop();

    std::shared_ptr<FrameBuffer> m_Buffer;
    std::unique_ptr<CameraHandler> m_Camera;
    std::unique_ptr<VideoHandler> m_Video;
    
    std::atomic<bool> m_Running;
    std::thread m_Thread;
    uint64_t m_FrameCounter;
};
