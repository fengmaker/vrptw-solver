cmake_minimum_required(VERSION 3.10)
project(pricing_lib_project)

# ==========================================
# 1. 核心修复：设置默认构建模式为 Release
# ==========================================
# 如果用户没有指定模式（比如直接运行 cmake ..），默认设为 Release。
# Release 模式会自动加上 /O2，Debug 模式会自动加上 /RTC1，避免冲突。
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    message(STATUS "No build type selected, defaulting to Release")
    set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Build type (Debug, Release)" FORCE)
endif()

# 2. 设置 C++ 标准
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 3. 查找 Python (保持你原本的逻辑)
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)

# 4. 查找 Pybind11 (保持你原本的逻辑)
execute_process(
    COMMAND "${Python3_EXECUTABLE}" -c "import pybind11; print(pybind11.get_cmake_dir())"
    OUTPUT_VARIABLE pybind11_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
message(STATUS "Found pybind11 CMake dir: ${pybind11_DIR}")
find_package(pybind11 CONFIG REQUIRED)

# 5. 查找源文件
file(GLOB_RECURSE SOURCES "cpp_src/*.cpp")

# 6. 创建模块
pybind11_add_module(pricing_lib ${SOURCES})

# 7. 添加头文件路径
target_include_directories(pricing_lib PRIVATE "cpp_src")

# ==========================================
# 8. 编译参数 (修改后)
# ==========================================
if(MSVC)
    # Windows 专用参数
    target_compile_options(pricing_lib PRIVATE 
        /utf-8          # 解决中文注释乱码
        /EHsc           # 启用标准 C++ 异常
        /W3             # 警告级别 3
        /bigobj         # 防止因为模板展开过大导致的目标文件过大错误
    )
    
    # 【注意】我们在这里 *不* 手动添加 /O2。
    # CMake 会根据 CMAKE_BUILD_TYPE=Release 自动添加 /O2。
    # CMake 会根据 CMAKE_BUILD_TYPE=Debug 自动添加 /RTC1。
    # 这样就永远不会出现冲突了。
    
else()
    # Linux/Mac 参数
    target_compile_options(pricing_lib PRIVATE 
        -Wall
        -Wextra
    )
    # 同样，Linux 下 Release 模式也会自动加 -O3
endif()