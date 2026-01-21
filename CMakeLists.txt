cmake_minimum_required(VERSION 3.10)
project(pricing_lib_project)

# 1. 设置 C++ 标准 (对应 /std:c++17)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 1. 先找到 Python 解释器（这一步很关键，确保用的是你当前环境的 Python）
# 新代码（加上 Development 组件）
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)

# 2. 运行一个小脚本，让 Python 打印出 pybind11 的 CMake 路径
# 相当于在终端运行：python -c "import pybind11; print(pybind11.get_cmake_dir())"
execute_process(
    COMMAND "${Python3_EXECUTABLE}" -c "import pybind11; print(pybind11.get_cmake_dir())"
    OUTPUT_VARIABLE pybind11_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)

# 3. 打印一下找到的路径（方便调试，如果报错可以看到这里是不是空的）
message(STATUS "Found pybind11 CMake dir: ${pybind11_DIR}")

# 4. 现在告诉 CMake 去这个路径找配置
find_package(pybind11 CONFIG REQUIRED)

# 3. 查找源文件 (对应 glob.glob("cpp_src/*.cpp"))
# 这里把 cpp_src 目录下所有的 .cpp 文件找出来存到 SOURCES 变量里
file(GLOB_RECURSE SOURCES "cpp_src/*.cpp")

# 4. 创建 Python 模块 (对应 name="pricing_lib")
# 这里的 "pricing_lib" 必须和你的 PYBIND11_MODULE(pricing_lib, m) 里的名字一致
pybind11_add_module(pricing_lib ${SOURCES})

# 5. 添加头文件路径 (对应 include_dirs=["cpp_src"])
target_include_directories(pricing_lib PRIVATE "cpp_src")

# 6. 设置编译参数 (对应 extra_compile_args)
if(MSVC)
    # Windows 参数
    target_compile_options(pricing_lib PRIVATE 
        /O2        # 优化
        /utf-8     # 解决中文编码警告 C4819
        /EHsc      # 异常处理
        /W3        # 警告级别
    )
else()
    # Linux/Mac 参数
    target_compile_options(pricing_lib PRIVATE 
        -O3 
        -Wall
    )
endif()