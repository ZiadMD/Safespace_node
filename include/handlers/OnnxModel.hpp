#pragma once

#include <string>
#include <vector>
#include <opencv2/opencv.hpp>
#include "utils/Types.hpp"

// Placeholder for ONNX features
// #include <onnxruntime_cxx_api.h> // Will link via CMake

class OnnxModel {
public:
    OnnxModel(const std::string& model_path);
    ~OnnxModel();

    void load();
    std::vector<Constants::BoundingBox> infer(const cv::Mat& frame, float confidence_thresh = 0.5f);

private:
    std::string m_Path;
    bool m_Loaded;
    
    // Ort::Env m_Env;
    // Ort::Session m_Session;
};
