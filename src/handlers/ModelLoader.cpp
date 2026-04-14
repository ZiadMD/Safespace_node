#include "handlers/ModelLoader.hpp"
#include "handlers/OnnxModel.hpp"
#include "utils/Config.hpp"
#include "utils/Logger.hpp"

ModelLoader& ModelLoader::getInstance() {
    static ModelLoader instance;
    return instance;
}

void ModelLoader::loadConfiguredModels() {
    // Abstract check for iterating config.yaml and loading registered models
    Logger::info("Loading all AI models...");
    
    // Example: Mock fallback wrapper
    auto fallback = std::make_shared<OnnxModel>("models/yolov8_optimized.onnx");
    fallback->load();
    m_Models["yolo"] = fallback;
}

std::shared_ptr<OnnxModel> ModelLoader::getModel(const std::string& name) {
    if (m_Models.find(name) != m_Models.end()) {
        return m_Models[name];
    }
    return nullptr;
}

std::vector<std::string> ModelLoader::getActiveModels() const {
    std::vector<std::string> list;
    for (const auto& [name, model] : m_Models) list.push_back(name);
    return list;
}
