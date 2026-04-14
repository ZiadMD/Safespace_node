#include "handlers/CameraHandler.hpp"
#include "utils/Logger.hpp"

CameraHandler::CameraHandler(int camera_id, int width, int height, int fps)
    : m_CameraId(camera_id), m_Width(width), m_Height(height), m_Fps(fps) {}

CameraHandler::~CameraHandler() { stop(); }

bool CameraHandler::start() {
    Logger::info("Starting camera " + std::to_string(m_CameraId));
    // E.g., Use V4L2 natively on Linux if preferred
    m_Capture.open(m_CameraId, cv::CAP_ANY);
    if (!m_Capture.isOpened()) {
        Logger::error("Failed to open camera");
        return false;
    }
    m_Capture.set(cv::CAP_PROP_FRAME_WIDTH, m_Width);
    m_Capture.set(cv::CAP_PROP_FRAME_HEIGHT, m_Height);
    m_Capture.set(cv::CAP_PROP_FPS, m_Fps);
    return true;
}

void CameraHandler::stop() {
    if (m_Capture.isOpened()) {
        m_Capture.release();
    }
}

bool CameraHandler::readFrame(cv::Mat& out_frame) {
    if (!m_Capture.isOpened()) return false;
    return m_Capture.read(out_frame);
}

bool CameraHandler::isOpened() const {
    return m_Capture.isOpened();
}
