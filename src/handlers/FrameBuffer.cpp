#include "handlers/FrameBuffer.hpp"

FrameBuffer::FrameBuffer(int max_seconds, int fps) {
    m_Capacity = static_cast<size_t>(max_seconds * fps);
}

void FrameBuffer::write(const Core::SharedFrame& frame) {
    std::lock_guard<std::mutex> lock(m_Mutex);
    if (m_Buffer.size() >= m_Capacity && m_Capacity > 0) {
        m_Buffer.pop_front();
    }
    m_Buffer.push_back(frame);
}

Core::SharedFrame FrameBuffer::getLatest() const {
    std::lock_guard<std::mutex> lock(m_Mutex);
    if (m_Buffer.empty()) {
        return Core::SharedFrame{};
    }
    return m_Buffer.back();
}
