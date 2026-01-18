// cpp_src/label.h
#pragma once
#include <vector>
#include <cstdint> // for uint64_t

// 标签结构体
// 使用索引(int)代替指针，防止 vector 扩容导致指针失效
struct Label {
    int node_id;
    int parent_index; // 指向 label_pool 中的父节点索引，-1 表示根
    
    double cost;      // Reduced Cost
    double time;      // 累积时间 (Resource 1)
    int load;         // 累积负载 (Resource 2)
    
    // 多字位图：支持任意数量的节点
    // mask[0] 存节点 0-63, mask[1] 存 64-127...
    std::vector<uint64_t> visited_mask; 
    
    bool active;      // 用于标记是否被支配（延迟删除）
};