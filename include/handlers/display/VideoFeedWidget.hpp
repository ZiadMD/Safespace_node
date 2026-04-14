#pragma once

#include <QOpenGLWidget>
#include <QTimer>
#include <mutex>
#include <memory>
#include <opencv2/opencv.hpp>
#include "utils/Types.hpp"

class VideoFeedWidget : public QOpenGLWidget {
    Q_OBJECT

public:
    explicit VideoFeedWidget(QWidget *parent = nullptr);
    ~VideoFeedWidget() override;

    // Direct thread-safe frame setter injected via EventBus
    void setLatestFrame(const Core::SharedFrame& frame);

protected:
    void paintEvent(QPaintEvent *event) override;

private slots:
    void pullFrame();

private:
    QTimer* m_PullTimer;
    
    std::mutex m_Mutex;
    Core::SharedFrame m_LatestFrame;
    QImage m_QtImage;
};
