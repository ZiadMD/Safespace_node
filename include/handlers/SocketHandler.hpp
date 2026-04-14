#pragma once

#include <string>
#include <functional>
#include <unordered_map>

class SocketHandler {
public:
    SocketHandler();
    ~SocketHandler();

    bool connect(const std::string& url);
    void disconnect();
    void emit(const std::string& event_name, const std::string& payload);
    void on(const std::string& event_name, std::function<void(const std::string&)> callback);

private:
    bool m_Connected;
    // TODO: include sio_client or websocket client instance
    std::unordered_map<std::string, std::function<void(const std::string&)>> m_Callbacks;
};
