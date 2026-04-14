#include "handlers/display/DisplayHandler.hpp"
#include "handlers/display/MainWindow.hpp"

DisplayHandler::DisplayHandler() {}

DisplayHandler::~DisplayHandler() {}

void DisplayHandler::init() {
    m_MainWindow = std::make_unique<MainWindow>();
}

void DisplayHandler::show() {
    if (m_MainWindow) {
        m_MainWindow->show();
    }
}
