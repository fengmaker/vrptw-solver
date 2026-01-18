#include <pybind11/pybind11.h>
#include <pybind11/stl.h> // <--- 关键！让 C++ vector 自动变成 Python List
#include "dominance.h"    // 只需要引用头文件即可

namespace py = pybind11;

PYBIND11_MODULE(pricing_lib, m) {
    m.doc() = "High-performance VRP Pricing Accelerator";

    py::class_<DominanceChecker>(m, "DominanceChecker")
        .def(py::init<int>(), "Initialize with number of nodes")
        .def("is_dominated", &DominanceChecker::is_dominated, 
             "Check if a label is dominated by existing ones")
        .def("add_label", &DominanceChecker::add_label, 
             "Add a label to the pool")
        .def("clear", &DominanceChecker::clear, 
             "Clear all labels");
}