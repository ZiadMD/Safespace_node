#include "handlers/SocketHandler.hpp"
#include "utils/Logger.hpp"

SocketHandler::SocketHandler() : m_Connected(false) {}

SocketHandler::~SocketHandler() { disconnect(); }

bool SocketHandler::connect(const std::string& url) {
    Logger::info("Connecting to websocket server: " + url);
    // Placeholder logic
    m_Connected = true;
    return true;
}

void SocketHandler::disconnect() {
    if (m_Connected) {
        Logger::info("Disconnected from server.");
        m_Connected = false;
    }
}

void SocketHandler::emit(const std::string& event_name, const std::string& payload) {
    if (!m_Connected) return;
    // Logger::debug("Emitting event: " + event_name);
}

void SocketHandler::on(const std::string& event_name, std::function<void(const std::string&)> callback) {
    m_Callbacks[event_name] = callback;
    // Register natively with raw client
}
