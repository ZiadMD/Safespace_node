#include "managers/OutputManager.hpp"
#include "handlers/display/DisplayHandler.hpp"
#include "utils/EventBus.hpp"
#include "utils/Logger.hpp"

OutputManager::OutputManager() {
    m_Display = std::make_unique<DisplayHandler>();
}

OutputManager::~OutputManager() { stop(); }

void OutputManager::start() {
    m_Display->init();
    setupEventSubscriptions();
    m_Display->show();
}

void OutputManager::stop() {
    // Teardown logic
}

void OutputManager::setupEventSubscriptions() {
    Core::EventBus::getInstance().subscribe(Core::EventType::SERVER_COMMAND_RECEIVED, 
        [this](const std::any& payload) {
            // Forward command to display
            Logger::info("OutputManager forwarding server command to UI.");
        });
        
    Core::EventBus::getInstance().subscribe(Core::EventType::DETECTION_FOUND, 
        [this](const std::any& payload) {
            // Push detection frame to GUI
        });
}
