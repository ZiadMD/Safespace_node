#pragma once

#include <memory>

class MainWindow;

class DisplayHandler {
public:
    DisplayHandler();
    ~DisplayHandler();

    void init();
    void show();

private:
    std::unique_ptr<MainWindow> m_MainWindow;
};
