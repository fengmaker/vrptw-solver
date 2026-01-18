from setuptools import setup, Extension
import pybind11
import glob
import sys
import platform

# 自动查找 cpp_src 目录下的所有 .cpp 文件
# 注意：确保你已经删除了 dominance.cpp，否则这里还是会把旧文件加进去报错
cpp_sources = glob.glob("cpp_src/*.cpp")

# 根据操作系统设定编译参数
if sys.platform == "win32":
    # Windows (MSVC) 参数
    extra_compile_args = [
        '/O2',           # 优化级别 2
        '/std:c++17',    # C++17 标准
        '/utf-8',        # [关键] 解决中文注释导致的 C4819 警告
        '/EHsc'          # 启用 C++ 异常处理
    ]
else:
    # Linux / Mac (GCC/Clang) 参数
    extra_compile_args = [
        '-O3', 
        '-std=c++17'
    ]

ext_modules = [
    Extension(
        "pricing_lib",
        cpp_sources,
        include_dirs=[
            pybind11.get_include(),
            "cpp_src"  # 确保能找到头文件
        ],
        language='c++',
        extra_compile_args=extra_compile_args,
    ),
]

setup(
    name="pricing_lib",
    version="0.2",
    ext_modules=ext_modules,
)