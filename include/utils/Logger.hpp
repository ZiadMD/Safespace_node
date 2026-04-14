#pragma once

#include <string>
#include <memory>

class Logger {
public:
    static void init(const std::string& level = "INFO", bool file_logging = true);
    
    static void info(const std::string& msg);
    static void warn(const std::string& msg);
    static void error(const std::string& msg);
    static void debug(const std::string& msg);
};
