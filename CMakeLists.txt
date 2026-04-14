cmake_minimum_required(VERSION 3.16)
project(safespace-node VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

# Find necessary packages
find_package(OpenCV REQUIRED)
find_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets OpenGLWidgets)
find_package(Boost REQUIRED COMPONENTS system thread)
find_package(Threads REQUIRED)

# Include directories
include_directories(
    ${PROJECT_SOURCE_DIR}/include
    ${PROJECT_SOURCE_DIR}/src
    ${OpenCV_INCLUDE_DIRS}
    ${Boost_INCLUDE_DIRS}
)

# Collect source files
file(GLOB_RECURSE SRC_FILES 
    "src/*.cpp"
    "include/*.hpp"
)

# Executable
add_executable(${PROJECT_NAME} ${SRC_FILES})

# Link libraries
target_link_libraries(${PROJECT_NAME} PRIVATE
    ${OpenCV_LIBS}
    Qt6::Core Qt6::Gui Qt6::Widgets Qt6::OpenGLWidgets
    Boost::system Boost::thread
    Threads::Threads
    # TODO: Add ONNX Runtime and Socket.IO dependencies properly once downloaded/installed
)
