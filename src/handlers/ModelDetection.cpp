#include "handlers/ModelDetection.hpp"
#include <opencv2/dnn.hpp>
#include <opencv2/imgproc.hpp>

std::vector<Constants::BoundingBox> ModelDetection::nonMaximumSuppression(
        const std::vector<Constants::BoundingBox>& boxes, float iou_thresh) {
        
    std::vector<cv::Rect> rects;
    std::vector<float> scores;
    
    for (const auto& b : boxes) {
        rects.push_back(cv::Rect(b.x, b.y, b.width, b.height));
        scores.push_back(b.confidence);
    }
    
    std::vector<int> indices;
    cv::dnn::NMSBoxes(rects, scores, 0.0f, iou_thresh, indices);
    
    std::vector<Constants::BoundingBox> nms_boxes;
    for (int i : indices) {
        nms_boxes.push_back(boxes[i]);
    }
    return nms_boxes;
}

void ModelDetection::drawAnnotations(cv::Mat& frame, const std::vector<Constants::BoundingBox>& detections) {
    for (const auto& b : detections) {
        cv::Rect r(b.x, b.y, b.width, b.height);
        cv::rectangle(frame, r, cv::Scalar(0, 255, 0), 2);
        
        std::string label = b.class_name + " " + std::to_string(b.confidence);
        cv::putText(frame, label, cv::Point(b.x, b.y - 5), cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 255, 0), 1);
    }
}
