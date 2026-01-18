#include <pybind11/pybind11.h>
#include <cmath>

namespace py = pybind11;

// 一个简单的 C++ 函数
double calculate_distance(double x1, double y1, double x2, double y2) {
    return std::sqrt(std::pow(x1 - x2, 2) + std::pow(y1 - y2, 2));
}

// 绑定代码
PYBIND11_MODULE(pricing_lib, m) {
    m.doc() = "My VRP C++ Accelerator"; // 模块说明
    m.def("calc_dist", &calculate_distance, "A function to calculate distance");
}