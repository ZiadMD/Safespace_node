#include "handlers/VideoHandler.hpp"
#include "utils/Logger.hpp"

VideoHandler::VideoHandler(const std::string& path, bool loop)
    : m_Path(path), m_Loop(loop) {}

VideoHandler::~VideoHandler() { stop(); }

bool VideoHandler::start() {
    Logger::info("Loading video " + m_Path);
    m_Capture.open(m_Path);
    return m_Capture.isOpened();
}

void VideoHandler::stop() {
    if (m_Capture.isOpened()) {
        m_Capture.release();
    }
}

bool VideoHandler::readFrame(cv::Mat& out_frame) {
    if (!m_Capture.isOpened()) return false;
    
    bool ret = m_Capture.read(out_frame);
    if (!ret && m_Loop) {
        // Loop back to start
        m_Capture.set(cv::CAP_PROP_POS_FRAMES, 0);
        ret = m_Capture.read(out_frame);
    }
    return ret;
}

bool VideoHandler::isOpened() const {
    return m_Capture.isOpened();
}
