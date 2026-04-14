#include "managers/NetworkManager.hpp"
#include "handlers/SocketHandler.hpp"
#include "utils/EventBus.hpp"
#include "utils/Logger.hpp"
#include <chrono>

NetworkManager::NetworkManager() 
    : m_Running(false), m_HeartbeatInterval(5), m_LastAccidentReport(0) {
    m_Socket = std::make_unique<SocketHandler>();
}

NetworkManager::~NetworkManager() { stop(); }

void NetworkManager::start() {
    if (m_Running) return;

    if (m_Socket->connect("http://localhost:3000")) {
        setupSocketHandlers();
        m_Running = true;
        m_HeartbeatThread = std::thread(&NetworkManager::heartbeatLoop, this);
    }
}

void NetworkManager::stop() {
    m_Running = false;
    if (m_HeartbeatThread.joinable()) {
        m_HeartbeatThread.join();
    }
    if (m_Socket) {
        m_Socket->disconnect();
    }
}

void NetworkManager::setupSocketHandlers() {
    m_Socket->on("command", [](const std::string& payload) {
        Logger::info("Received command from server: " + payload);
        Core::EventBus::getInstance().publish(Core::EventType::SERVER_COMMAND_RECEIVED, payload);
    });
}

void NetworkManager::reportAccident(const Core::DetectionResult& result) {
    // Basic cooldown logic (1 second cooldown)
    double now = std::chrono::duration_cast<std::chrono::milliseconds>(
                 std::chrono::system_clock::now().time_since_epoch()).count() / 1000.0;
                 
    if (now - m_LastAccidentReport < 1.0) {
        return; 
    }
    
    m_LastAccidentReport = now;
    Logger::warn("Reporting accident to Central Unit!");
    
    // Base64 encode result.annotated_frame here and JSON encode bounding boxes
    std::string payload = "{\"type\":\"accident\", \"boxes\":" + std::to_string(result.boxes.size()) + "}";
    m_Socket->emit("node_accident_detected", payload);
}

void NetworkManager::heartbeatLoop() {
    Logger::info("Heartbeat thread started.");
    while(m_Running) {
        // Collect metrics like CPU, RAM, etc.
        std::string metrics = "{\"cpu\": 25.5, \"mem\": 1024}";
        // Send HTTP POST or emit Socket
        m_Socket->emit("heartbeat", metrics);
        
        // C++ alternative to range sleep chunking
        for(int i=0; i < m_HeartbeatInterval * 10 && m_Running; i++) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }
}
