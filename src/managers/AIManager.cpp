#include "managers/AIManager.hpp"
#include "handlers/FrameBuffer.hpp"
#include "handlers/ModelLoader.hpp"
#include "handlers/ModelDetection.hpp"
#include "utils/EventBus.hpp"
#include "utils/Logger.hpp"
#include <chrono>

AIManager::AIManager(std::shared_ptr<FrameBuffer> buffer)
    : m_Buffer(buffer), m_Running(false) {}

AIManager::~AIManager() { stop(); }

void AIManager::start() {
    if (m_Running) return;
    
    ModelLoader::getInstance().loadConfiguredModels();
    
    m_Running = true;
    m_Thread = std::thread(&AIManager::loop, this);
}

void AIManager::stop() {
    m_Running = false;
    if (m_Thread.joinable()) {
        m_Thread.join();
    }
}

void AIManager::loop() {
    Logger::info("AI Inference thread started");
    
    while(m_Running) {
        if (!m_Buffer) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            continue;
        }
        
        Core::SharedFrame sf = m_Buffer->getLatest();
        if (!sf.mat || sf.mat->empty()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            continue;
        }

        auto active_models = ModelLoader::getInstance().getActiveModels();
        std::vector<Constants::BoundingBox> all_detections;
        
        for (const auto& name : active_models) {
            auto model = ModelLoader::getInstance().getModel(name);
            if (model) {
                auto detections = model->infer(*sf.mat);
                all_detections.insert(all_detections.end(), detections.begin(), detections.end());
            }
        }
        
        if (!all_detections.empty()) {
            // Apply aggregate NMS
            auto final_boxes = ModelDetection::nonMaximumSuppression(all_detections, 0.45f);
            
            // Draw
            std::shared_ptr<cv::Mat> annotated = std::make_shared<cv::Mat>(sf.mat->clone());
            ModelDetection::drawAnnotations(*annotated, final_boxes);
            
            Core::DetectionResult res{ final_boxes, annotated, sf.timestamp };
            Core::EventBus::getInstance().publish(Core::EventType::DETECTION_FOUND, res);
        }
        
        // Prevent 100% CPU lock in zero frames waiting cycle
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
}
