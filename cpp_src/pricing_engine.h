#ifndef PRICING_ENGINE_H
#define PRICING_ENGINE_H

#include <vector>
#include <cmath>
#include <algorithm>
#include <cstring> // for memset
#include <iostream>

// 1. 定义高性能 Bitset (放在 struct 定义之前)
struct FastBitset {
    uint64_t bits[4]; // 支持 4*64 = 256 个节点

    FastBitset() { memset(bits, 0, sizeof(bits)); }

    void set(int idx) {
        if (idx >= 0 && idx < 256) bits[idx >> 6] |= (1ULL << (idx & 63));
    }

    bool test(int idx) const {
        if (idx < 0 || idx >= 256) return false;
        return (bits[idx >> 6] & (1ULL << (idx & 63))) != 0;
    }

    // 判断 this 是否是 other 的子集
    bool is_subset_of(const FastBitset& other) const {
        for(int i=0; i<4; ++i) {
            if ((bits[i] & other.bits[i]) != bits[i]) return false;
        }
        return true;
    }

    // ng-route 核心逻辑：生成去往 next_node 时的访问状态
    // 新状态 = (当前状态 & next_node 的记忆集) | {next_node}
    FastBitset apply_ng_relaxation(const FastBitset& ng_mask, int next_node) const {
        FastBitset res;
        for(int i=0; i<4; ++i) {
            res.bits[i] = bits[i] & ng_mask.bits[i];
        }
        res.set(next_node);
        return res;
    }
};

// 2. 修改 ProblemData
struct ProblemData {
    int num_nodes;
    int vehicle_capacity;
    std::vector<int> demands;
    std::vector<double> service_times;
    std::vector<double> tw_start;
    std::vector<double> tw_end;
    std::vector<std::vector<double>> dist_matrix;
    std::vector<std::vector<double>> time_matrix;
    std::vector<std::vector<int>> neighbors; 

    // === 新增部分 ===
    // 1. Python 传进来的原始数据 (List[List[int]])
    std::vector<std::vector<int>> ng_neighbor_lists; 
    
    // 2. C++ 内部转换后的 Bitset 数组 (用于计算)
    std::vector<FastBitset> ng_masks; 
};

// 3. 修改 Label
struct Label {
    int node_id;
    int parent_index;
    double cost;
    double time;
    int load;
    FastBitset visited_mask; // 替换原来的 vector<uint64>
    bool active;
};

class LabelingSolver {
public:
    LabelingSolver(ProblemData p_data, double p_bucket_step);
    std::vector<std::vector<int>> solve(const std::vector<double>& duals);

private:
    ProblemData data;
    double bucket_step;
    std::vector<Label> label_pool;
    std::vector<std::vector<int>> dominance_sets;
    std::vector<std::vector<int>> buckets;

    bool check_and_update_dominance(int node, const Label& new_label);
};

#endif