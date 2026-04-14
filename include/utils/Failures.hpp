#pragma once

#include <string>
#include <unordered_map>
#include <mutex>

struct FailureRecord {
    int count = 0;
    long last_failure_timestamp = 0;
};

class FailureManager {
public:
    FailureManager(int threshold = 5, int window_seconds = 300);
    
    void recordFailure(const std::string& system);
    void resetFailure(const std::string& system);
    bool isSystemFailing(const std::string& system);

private:
    int m_Threshold;
    int m_WindowSeconds;
    std::unordered_map<std::string, FailureRecord> m_Records;
    std::mutex m_Mutex;
};
