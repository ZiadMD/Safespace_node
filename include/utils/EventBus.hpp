#pragma once

#include <functional>
#include <map>
#include <vector>
#include <mutex>
#include <any>
#include "utils/Types.hpp"

namespace Core {

class EventBus {
public:
    using Callback = std::function<void(const std::any&)>;

    static EventBus& getInstance() {
        static EventBus instance;
        return instance;
    }

    void subscribe(EventType type, Callback callback);
    void publish(EventType type, const std::any& payload);

private:
    EventBus() = default;
    EventBus(const EventBus&) = delete;
    EventBus& operator=(const EventBus&) = delete;

    std::map<EventType, std::vector<Callback>> m_Subscribers;
    std::mutex m_Mutex;
};

} // namespace Core
