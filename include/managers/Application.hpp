#pragma once

#include <memory>
#include <atomic>

class InputManager;
class AIManager;
class NetworkManager;
class OutputManager;

namespace Core {

class Application {
public:
    Application();
    ~Application();

    void init();
    void run();
    void stop();

private:
    std::atomic<bool> m_Running{false};

    std::unique_ptr<InputManager> m_InputManager;
    std::unique_ptr<AIManager> m_AIManager;
    std::unique_ptr<NetworkManager> m_NetworkManager;
    std::unique_ptr<OutputManager> m_OutputManager;
};

} // namespace Core
