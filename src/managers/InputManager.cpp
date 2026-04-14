#include "managers/InputManager.hpp"
#include "handlers/CameraHandler.hpp"
#include "handlers/VideoHandler.hpp"
#include "handlers/FrameBuffer.hpp"
#include "utils/EventBus.hpp"
#include "utils/Logger.hpp"
#include "utils/Config.hpp"
#include <chrono>

InputManager::InputManager(std::shared_ptr<FrameBuffer> buffer) 
    : m_Buffer(buffer), m_Running(false), m_FrameCounter(0) {
    
    // Abstract logic: if video path is provided in config, use VideoHandler, else CameraHandler
    std::string video_path = ""; // Config::getInstance().get<std::string>("video.test.path", "");
    
    if (!video_path.empty()) {
        m_Video = std::make_unique<VideoHandler>(video_path);
    } else {
        m_Camera = std::make_unique<CameraHandler>();
    }
}

InputManager::~InputManager() { stop(); }

void InputManager::start() {
    if (m_Running) return;
    
    bool started = false;
    if (m_Video) started = m_Video->start();
    else if (m_Camera) started = m_Camera->start();

    if (!started) {
        Logger::error("Input source failed to start.");
        return;
    }

    m_Running = true;
    m_Thread = std::thread(&InputManager::loop, this);
}

void InputManager::stop() {
    m_Running = false;
    if (m_Thread.joinable()) {
        m_Thread.join();
    }
    if (m_Video) m_Video->stop();
    if (m_Camera) m_Camera->stop();
}

void InputManager::loop() {
    Logger::info("Input Capture loop started.");
    
    while(m_Running) {
        cv::Mat frame;
        bool ret = false;
        
        if (m_Video) ret = m_Video->readFrame(frame);
        else if (m_Camera) ret = m_Camera->readFrame(frame);

        if (ret && !frame.empty()) {
            double ts = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()).count() / 1000.0;
                
            Core::SharedFrame sf{ std::make_shared<cv::Mat>(frame.clone()), ts, m_FrameCounter++ };
            
            if (m_Buffer) m_Buffer->write(sf);
            Core::EventBus::getInstance().publish(Core::EventType::FRAME_CAPTURED, sf);
        } else {
            // Sleep short duration if empty frame
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    }
}
