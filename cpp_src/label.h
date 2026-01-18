#pragma once // 防止头文件被重复引用
#include <vector>

// Label 结构体定义
// 注意：这里没有 Python 的任何东西，只有纯 C++ 类型
struct Label {
    int node;
    double cost;
    double time;
    int load;
    
    // 使用 vector 来存储多字位图 (Multi-word Bitset)
    // 能够支持无限数量的节点 (100, 1000, 10000...)
    std::vector<unsigned long long> visited_mask; 
};