#include "handlers/OnnxModel.hpp"
#include "utils/Logger.hpp"

OnnxModel::OnnxModel(const std::string& model_path) : m_Path(model_path), m_Loaded(false) {}

OnnxModel::~OnnxModel() {}

void OnnxModel::load() {
    Logger::info("Loading ONNX Model from: " + m_Path);
    // TODO: Init Ort::Env and Ort::Session
    m_Loaded = true;
}

std::vector<Constants::BoundingBox> OnnxModel::infer(const cv::Mat& frame, float confidence_thresh) {
    std::vector<Constants::BoundingBox> results;
    if (!m_Loaded) return results;
    
    // TODO: cv::dnn::blobFromImage or manual CHW processing
    // result.push_back({x, y, w, h, conf, "class"});
    
    return results;
}
