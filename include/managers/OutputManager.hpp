#pragma once

#include <memory>
class DisplayHandler;

class OutputManager {
public:
    OutputManager();
    ~OutputManager();

    void start();
    void stop();

private:
    void setupEventSubscriptions();

    std::unique_ptr<DisplayHandler> m_Display;
};
