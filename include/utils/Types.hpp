#pragma once
#include <memory>
#include <opencv2/opencv.hpp>
#include <string>

namespace Core {
    struct SharedFrame {
        std::shared_ptr<cv::Mat> mat;
        long long timestamp;
        int frameId;
    };
    
    enum class EventType {
        FRAME_CAPTURED,
        DETECTION_FOUND,
        SERVER_COMMAND_RECEIVED,
        ERROR_OCCURRED
    };
}
