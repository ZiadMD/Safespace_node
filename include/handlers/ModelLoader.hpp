#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <memory>

class OnnxModel;

class ModelLoader {
public:
    static ModelLoader& getInstance();
    
    void loadConfiguredModels();
    std::shared_ptr<OnnxModel> getModel(const std::string& name);
    std::vector<std::string> getActiveModels() const;

private:
    ModelLoader() = default;
    
    std::unordered_map<std::string, std::shared_ptr<OnnxModel>> m_Models;
};
