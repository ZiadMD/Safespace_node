#pragma once
#include <opencv2/opencv.hpp>
#include <string>

class VideoHandler {
public:
    VideoHandler(const std::string& path, bool loop = true);
    ~VideoHandler();

    bool start();
    void stop();
    bool readFrame(cv::Mat& out_frame);
    bool isOpened() const;

private:
    std::string m_Path;
    bool m_Loop;
    cv::VideoCapture m_Capture;
};
