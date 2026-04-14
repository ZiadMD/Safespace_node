#pragma once

#include "utils/Types.hpp"
#include <memory>
#include <vector>

class OnnxModel;

class ModelDetection {
public:
    static std::vector<Constants::BoundingBox> nonMaximumSuppression(
        const std::vector<Constants::BoundingBox>& boxes, float iou_thresh);
        
    static void drawAnnotations(cv::Mat& frame, const std::vector<Constants::BoundingBox>& detections);
};
