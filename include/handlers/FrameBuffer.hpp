#pragma once

#include <deque>
#include <mutex>
#include "utils/Types.hpp"

class FrameBuffer {
public:
    FrameBuffer(int max_seconds = 30, int fps = 30);
    
    void write(const Core::SharedFrame& frame);
    Core::SharedFrame getLatest() const;

private:
    size_t m_Capacity;
    std::deque<Core::SharedFrame> m_Buffer;
    mutable std::mutex m_Mutex;
};
