#pragma once

#include <memory>
#include <string>
#include <thread>
#include <atomic>
#include "utils/Types.hpp"

class SocketHandler;

class NetworkManager {
public:
    static NetworkManager& getInstance();
    NetworkManager();
    ~NetworkManager();

    void start();
    void stop();
    
    void reportAccident(const Core::DetectionResult& result);

private:
    void heartbeatLoop();
    void setupSocketHandlers();

    std::unique_ptr<SocketHandler> m_Socket;
    std::atomic<bool> m_Running;
    std::atomic<double> m_LastAccidentReport;
    std::thread m_HeartbeatThread;
    int m_HeartbeatInterval;
};
