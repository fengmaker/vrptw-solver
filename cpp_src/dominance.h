#pragma once
#include <vector>
#include "label.h" // 引用上面的 Label 定义

class DominanceChecker {
private:
    // 内存池：node_labels[i] 存储节点 i 上所有的标签
    std::vector<std::vector<Label>> node_labels; 

public:
    // 构造函数：初始化桶的数量
    DominanceChecker(int num_nodes);

    // 核心功能 1：检查是否被支配
    // const std::vector<...>& 表示“引用传递”，避免拷贝数组，速度极快
    bool is_dominated(int node, double cost, double time, int load, const std::vector<unsigned long long>& mask);

    // 核心功能 2：添加标签
    void add_label(int node, double cost, double time, int load, const std::vector<unsigned long long>& mask);

    // 清空所有标签（下一轮迭代前调用）
    void clear();
};