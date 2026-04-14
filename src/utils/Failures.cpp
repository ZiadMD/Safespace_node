#include "utils/Failures.hpp"
#include "utils/Logger.hpp"
#include <chrono>

FailureManager::FailureManager(int threshold, int window_seconds) 
    : m_Threshold(threshold), m_WindowSeconds(window_seconds) {}

void FailureManager::recordFailure(const std::string& system) {
    std::lock_guard<std::mutex> lock(m_Mutex);
    auto now = std::chrono::system_clock::now().time_since_epoch();
    long timestamp = std::chrono::duration_cast<std::chrono::seconds>(now).count();
    
    auto& record = m_Records[system];
    
    // Check if outside window
    if (timestamp - record.last_failure_timestamp > m_WindowSeconds) {
        record.count = 1;
    } else {
        record.count++;
    }
    record.last_failure_timestamp = timestamp;
    
    Logger::warn("Failure recorded in " + system + " (Count: " + std::to_string(record.count) + ")");
}

void FailureManager::resetFailure(const std::string& system) {
    std::lock_guard<std::mutex> lock(m_Mutex);
    m_Records[system] = FailureRecord();
    Logger::info("Failures reset for " + system);
}

bool FailureManager::isSystemFailing(const std::string& system) {
    std::lock_guard<std::mutex> lock(m_Mutex);
    auto it = m_Records.find(system);
    if (it != m_Records.end()) {
        return it->second.count >= m_Threshold;
    }
    return false;
}
