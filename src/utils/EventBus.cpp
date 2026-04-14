#include "utils/EventBus.hpp"

namespace Core {

void EventBus::subscribe(EventType type, Callback callback) {
    std::lock_guard<std::mutex> lock(m_Mutex);
    m_Subscribers[type].push_back(std::move(callback));
}

void EventBus::publish(EventType type, const std::any& payload) {
    std::lock_guard<std::mutex> lock(m_Mutex);
    auto it = m_Subscribers.find(type);
    if (it != m_Subscribers.end()) {
        for (const auto& cb : it->second) {
            cb(payload);
        }
    }
}

} // namespace Core
