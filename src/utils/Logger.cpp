#include "utils/Logger.hpp"
#include <iostream>
// TODO: Integrate spdlog implementation details

void Logger::init(const std::string& level, bool file_logging) {
    // Placeholder for spdlog instantiation
    std::cout << "[INFO] Logger initialized at level: " << level << std::endl;
}

void Logger::info(const std::string& msg) {
    std::cout << "[INFO] " << msg << std::endl;
}

void Logger::warn(const std::string& msg) {
    std::cerr << "[WARN] " << msg << std::endl;
}

void Logger::error(const std::string& msg) {
    std::cerr << "[ERROR] " << msg << std::endl;
}

void Logger::debug(const std::string& msg) {
    std::cout << "[DEBUG] " << msg << std::endl;
}
