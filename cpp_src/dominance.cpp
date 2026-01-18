#include "dominance.h" // 必须引用头文件，否则不知道类长什么样
#include <cmath>       // 用于浮点数比较

// 实现构造函数
DominanceChecker::DominanceChecker(int num_nodes) {
    node_labels.resize(num_nodes);
}

// 实现清空函数
void DominanceChecker::clear() {
    for (auto& vec : node_labels) {
        vec.clear();
    }
}

// 实现添加标签函数
void DominanceChecker::add_label(int node, double cost, double time, int load, const std::vector<unsigned long long>& mask) {
    // 直接在 vector 尾部构建对象，零拷贝
    node_labels[node].push_back({node, cost, time, load, mask});
}

// [核心] 实现优越性检查函数
bool DominanceChecker::is_dominated(int node, double cost, double time, int load, const std::vector<unsigned long long>& mask) {
    // 遍历当前节点已有的所有标签 (old)
    for (const auto& old : node_labels[node]) {
        
        // 1. 资源消耗检查 (Cost, Time, Load)
        // 如果 old 消耗的比 new 还多，那 old 肯定无法支配 new，直接跳过
        // 使用 1e-5 容差处理浮点数精度问题
        if (old.cost > cost + 1e-5 || 
            old.time > time + 1e-5 || 
            old.load > load) {
            continue; 
        }

        // 2. 访问集合 (Visited Mask) 检查
        // 规则：old 访问过的节点集合 必须是 new 访问过的节点集合的 子集
        // 数学表达： (Old_Set ⊆ New_Set)
        // 位运算表达： (Old_Mask & New_Mask) == Old_Mask
        
        bool mask_is_subset = true;
        
        // 因为 mask 是一个数组 (vector)，我们需要一段一段地比较
        size_t len = mask.size();
        for (size_t i = 0; i < len; ++i) {
            // 安全检查：防止数组越界（虽然理论上长度应该一致）
            if (i >= old.visited_mask.size()) break; 
            
            unsigned long long old_part = old.visited_mask[i];
            unsigned long long new_part = mask[i];
            
            // 如果某一段不满足子集关系，则整体不满足
            if ((old_part & new_part) != old_part) {
                mask_is_subset = false;
                break;
            }
        }

        // 如果资源更优，且路径是子集，则 new 被支配了（无用标签）
        if (mask_is_subset) {
            return true; 
        }
    }
    
    // 找遍了都没被支配，说明是个好标签
    return false;
}