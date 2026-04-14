#pragma once
#include <opencv2/opencv.hpp>

class CameraHandler {
public:
    CameraHandler(int camera_id = 0, int width = 640, int height = 640, int fps = 30);
    ~CameraHandler();

    bool start();
    void stop();
    bool readFrame(cv::Mat& out_frame);
    bool isOpened() const;

private:
    int m_CameraId;
    int m_Width;
    int m_Height;
    int m_Fps;
    cv::VideoCapture m_Capture;
};
