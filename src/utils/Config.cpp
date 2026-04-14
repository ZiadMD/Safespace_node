#include "utils/Config.hpp"
#include "utils/Logger.hpp"
#include <stdexcept>

Config& Config::getInstance() {
    static Config instance;
    return instance;
}

void Config::loadAll(const std::string& configs_dir) {
    Logger::info("Loading configurations from: " + configs_dir);
    // TODO: use std::filesystem to iterate JSON files 
    // and parse with nlohmann/json into m_Store
}
