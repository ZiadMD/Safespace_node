#include "handlers/display/MainWindow.hpp"
#include "handlers/display/VideoFeedWidget.hpp"
#include "handlers/display/SystemMonitorWidget.hpp"
#include "handlers/display/LaneWidget.hpp"
#include "handlers/display/SpeedWidget.hpp"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QWidget>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent) {
    setupUi();
}

MainWindow::~MainWindow() {}

void MainWindow::setupUi() {
    setWindowTitle("Safespace Node - C++");
    resize(1280, 720);

    QWidget* central = new QWidget(this);
    QVBoxLayout* mainLayout = new QVBoxLayout(central);

    m_VideoWidget = new VideoFeedWidget(this);
    m_SystemWidget = new SystemMonitorWidget(this);
    m_LaneWidget = new LaneWidget(this);
    m_SpeedWidget = new SpeedWidget(this);

    QHBoxLayout* topLayout = new QHBoxLayout();
    topLayout->addWidget(m_SystemWidget);
    topLayout->addWidget(m_SpeedWidget);
    
    mainLayout->addLayout(topLayout);
    mainLayout->addWidget(m_VideoWidget, 1); // 1 = stretch factor
    mainLayout->addWidget(m_LaneWidget);

    setCentralWidget(central);
}
