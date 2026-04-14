#pragma once

#include <string>
#include <unordered_map>
#include <any>

class Config {
public:
    static Config& getInstance();
    
    void loadAll(const std::string& configs_dir);
    
    template<typename T>
    T get(const std::string& key, const T& default_value) const;

    template<typename T>
    T get(const std::string& key) const;

private:
    Config() = default;
    
    // In-memory key-value store parsing nlohmann::json
    // Simulating dot notation e.g., "node.id"
    std::unordered_map<std::string, std::any> m_Store;
};
