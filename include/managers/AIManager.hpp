#pragma once

#include <memory>
#include <thread>
#include <atomic>

class FrameBuffer;

class AIManager {
public:
    AIManager(std::shared_ptr<FrameBuffer> buffer);
    ~AIManager();

    void start();
    void stop();

private:
    void loop();

    std::shared_ptr<FrameBuffer> m_Buffer;
    std::atomic<bool> m_Running;
    std::thread m_Thread;
};
