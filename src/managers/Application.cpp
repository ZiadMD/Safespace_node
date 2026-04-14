#include "managers/Application.hpp"
#include "managers/InputManager.hpp"
#include "managers/AIManager.hpp"
#include "managers/NetworkManager.hpp"
#include "managers/OutputManager.hpp"
#include "utils/Logger.hpp"

#include <thread>
#include <chrono>

namespace Core {

Application::Application() {
    m_InputManager = std::make_unique<InputManager>();
    m_AIManager = std::make_unique<AIManager>();
    m_NetworkManager = std::make_unique<NetworkManager>();
    m_OutputManager = std::make_unique<OutputManager>();
}

Application::~Application() {
    stop();
}

void Application::init() {
    Logger::info("Initializing Safespace Node...");
    m_NetworkManager->start();
    m_AIManager->start();
    m_InputManager->start();
    m_OutputManager->start();
}

void Application::run() {
    m_Running = true;
    Logger::info("Safespace Node is running.");
    // Main loop intentionally light or empty if UI thread controls flow.
}

void Application::stop() {
    m_Running = false;
    Logger::info("Stopping Safespace Node...");
    m_InputManager->stop();
    m_AIManager->stop();
    m_NetworkManager->stop();
    m_OutputManager->stop();
}

} // namespace Core
