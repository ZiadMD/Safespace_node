#pragma once

#include <QMainWindow>
#include <memory>

class VideoFeedWidget;
class SystemMonitorWidget;
class LaneWidget;
class SpeedWidget;

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

private:
    void setupUi();

    VideoFeedWidget* m_VideoWidget;
    SystemMonitorWidget* m_SystemWidget;
    LaneWidget* m_LaneWidget;
    SpeedWidget* m_SpeedWidget;
};
