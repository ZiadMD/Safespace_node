#include "handlers/display/VideoFeedWidget.hpp"
#include <QPainter>
#include "utils/EventBus.hpp"

VideoFeedWidget::VideoFeedWidget(QWidget *parent) : QOpenGLWidget(parent) {
    m_PullTimer = new QTimer(this);
    connect(m_PullTimer, &QTimer::timeout, this, &VideoFeedWidget::pullFrame);
    m_PullTimer->start(33); // ~30 FPS pull target
    
    // Subscribe tightly to events (or polled via OutputManager)
    Core::EventBus::getInstance().subscribe(Core::EventType::FRAME_CAPTURED,
        [this](const std::any& payload) {
            auto sf = std::any_cast<Core::SharedFrame>(payload);
            setLatestFrame(sf);
        });
}

VideoFeedWidget::~VideoFeedWidget() {}

void VideoFeedWidget::setLatestFrame(const Core::SharedFrame& frame) {
    std::lock_guard<std::mutex> lock(m_Mutex);
    m_LatestFrame = frame;
}

void VideoFeedWidget::pullFrame() {
    // If a new frame is present, queue a repaint
    update();
}

void VideoFeedWidget::paintEvent(QPaintEvent *event) {
    QPainter painter(this);
    
    std::lock_guard<std::mutex> lock(m_Mutex);
    if (m_LatestFrame.mat && !m_LatestFrame.mat->empty()) {
        // Warning: Requires BGR to RGB conversion for accurate colors.
        // We use Format_BGR888 to avoid doing cvtColor if possible.
        QImage img(m_LatestFrame.mat->data, 
                   m_LatestFrame.mat->cols, 
                   m_LatestFrame.mat->rows, 
                   m_LatestFrame.mat->step, 
                   QImage::Format_BGR888);
                   
        // Scale to fit widget while preserving aspect ratio
        QImage scaledImg = img.scaled(this->size(), Qt::KeepAspectRatio, Qt::SmoothTransformation);
        
        // Center drawing
        int x = (this->width() - scaledImg.width()) / 2;
        int y = (this->height() - scaledImg.height()) / 2;
        painter.drawImage(x, y, scaledImg);
    } else {
        painter.fillRect(this->rect(), Qt::black);
    }
}
