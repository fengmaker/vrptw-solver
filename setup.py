from setuptools import setup, Extension
import pybind11

# 获取 pybind11 的头文件路径
include_dirs = [pybind11.get_include()]

ext_modules = [
    Extension(
        "pricing_lib",           # 编译出来的模块名字
        ["pricing_cpp.cpp"],     # 源码文件
        include_dirs=include_dirs,
        language='c++'
    ),
]

setup(
    name="pricing_lib",
    version="0.0.1",
    ext_modules=ext_modules,
)