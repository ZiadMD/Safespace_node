#include "managers/Application.hpp"
#include "utils/Logger.hpp"
#include <QApplication>

int main(int argc, char* argv[]) {
    QApplication qtApp(argc, argv);
    
    Logger::init("INFO", true);
    
    Core::Application app;
    app.init();
    
    // In C++, the Application run logic doesn't block the Qt event loop
    // Qt itself handles the blocking execution.
    app.run();
    
    return qtApp.exec();
}
