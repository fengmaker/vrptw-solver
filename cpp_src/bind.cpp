// cpp_src/bind.cpp
#include <pybind11/pybind11.h>
#include <pybind11/stl.h> // 必须包含！负责 vector <-> list 转换
#include "pricing_engine.h"
namespace py = pybind11;

PYBIND11_MODULE(pricing_lib, m) {
    m.doc() = "High-performance VRP Pricing Engine (C++17)";

    // 1. 绑定 ProblemData 结构体
    // py::return_value_policy::copy 让 Python 拥有数据的副本，安全
    py::class_<ProblemData>(m, "ProblemData")
        .def(py::init<>())
        .def_readwrite("num_nodes", &ProblemData::num_nodes)
        .def_readwrite("vehicle_capacity", &ProblemData::vehicle_capacity)
        .def_readwrite("demands", &ProblemData::demands)
        .def_readwrite("service_times", &ProblemData::service_times)
        .def_readwrite("tw_start", &ProblemData::tw_start)
        .def_readwrite("tw_end", &ProblemData::tw_end)
        .def_readwrite("dist_matrix", &ProblemData::dist_matrix)
        .def_readwrite("time_matrix", &ProblemData::time_matrix)
        .def_readwrite("neighbors", &ProblemData::neighbors)
        .def_readwrite("ng_neighbor_lists", &ProblemData::ng_neighbor_lists);
    // 2. 绑定 LabelingSolver 类
    py::class_<LabelingSolver>(m, "LabelingSolver")
        .def(py::init<ProblemData, double>(), 
             py::arg("data"), py::arg("bucket_step"))
        // [修改] 绑定新的 solve 签名
        .def("solve", &LabelingSolver::solve, 
             py::arg("duals"),
             py::arg("forbidden_arcs") = std::vector<std::pair<int, int>>(), // 默认参数为空
             "Solve ESPPRC with duals and optional forbidden arcs");
}