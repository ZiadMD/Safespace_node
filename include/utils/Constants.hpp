#pragma once
#include <string>

namespace Constants {
    // Application Paths
    inline const std::string BASE_DIR = ".";
    inline const std::string ASSETS_DIR = BASE_DIR + "/assets";
    inline const std::string CONFIGS_DIR = BASE_DIR + "/configs";
    inline const std::string LOGS_DIR = BASE_DIR + "/logs";

    // Display
    enum class DisplayMode { DEV, PROD };

    // Failure Keys
    inline const std::string FAIL_CAMERA = "camera_error";
    inline const std::string FAIL_NETWORK = "network_error";
    inline const std::string FAIL_AI = "ai_error";
}
