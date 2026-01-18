from setuptools import setup, Extension
import pybind11
import glob  # <--- [神器] 自动查找文件

# 1. 自动找到 cpp_src 文件夹下所有的 .cpp 文件
# 以后你哪怕加了 100 个 cpp 文件，这里一行代码都不用改！
cpp_sources = glob.glob("cpp_src/*.cpp")

ext_modules = [
    Extension(
        "pricing_lib",        # 编译出来的包名
        cpp_sources,          # <--- 使用自动找到的文件列表
        include_dirs=[
            pybind11.get_include(),
            "cpp_src"         # <--- [重要] 告诉编译器头文件(.h)也在这里找
        ],
        language='c++',
    ),
]

setup(
    name="pricing_lib",
    version="0.1",
    ext_modules=ext_modules,
)