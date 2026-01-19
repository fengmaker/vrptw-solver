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
    bool intersects(const FastBitset& other, int split_node) const {
       for(int i=0; i<4; ++i) {
           // 两个集合的交集
           uint64_t common = bits[i] & other.bits[i];
           // 如果这一段里包含 0 或 split_node，我们要忽略它们
           // (因为 Depot 和 接合点 本来就该出现在两边)
           if (i == 0) { 
               // 假设 0 号节点在 bits[0] 的第 0 位
               common &= ~(1ULL << 0); 
           }
           int split_chunk = split_node >> 6;
           if (i == split_chunk) {
               common &= ~(1ULL << (split_node & 63));
           }
           
           if (common != 0) return true; // 还有其他重叠节点 -> 包含环路
       }
       return false;
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

// [新增] 定义紧凑的边结构，优化内存布局
struct Arc {
    int target;       // 目标节点 ID
    double cost;      // 预计算的 Reduced Cost (部分) 或 距离成本
    double duration;  // Travel Time + Service Time (预计算)
    double distance;  // 用于计算真实成本
    int demand;       // 资源消耗
};

// [新增] 桶图类：负责管理拓扑结构
class BucketGraph {
public:
    // 存储每个节点出发的“可行”边
    // vector index: from_node_id
    std::vector<std::vector<Arc>> nodes_outgoing_arcs;
    // 增加 bool is_backward 参数
    void build(const ProblemData& data, bool is_backward);
};

class LabelingSolver {
public:
    LabelingSolver(ProblemData p_data, double p_bucket_step);
    std::vector<std::vector<int>> solve(const std::vector<double>& duals);

private:
    ProblemData data;
    double bucket_step;
    // [新增] 两个图
    BucketGraph fwd_graph;
    BucketGraph bwd_graph;
    // [新增] 后向搜索的存储结构
    // 注意：前向用 label_pool，后向我们需要另一套 pool 或者共用
    // 为了清晰，建议分开存
    std::vector<Label> fwd_labels; 
    std::vector<Label> bwd_labels;
    // [新增] 每个节点上保留的标签索引 (用于 Merge)
    // nodes_fwd_labels[i] 存储节点 i 上所有存活的前向标签索引
    std::vector<std::vector<int>> nodes_fwd_labels;
    std::vector<std::vector<int>> nodes_bwd_labels;
    
    std::vector<Label> label_pool;
    std::vector<std::vector<int>> dominance_sets;
    std::vector<std::vector<int>> buckets;

    bool check_and_update_dominance(int node, const Label& new_label);
    // [新增] 辅助函数
    void run_forward_labeling(const std::vector<double>& duals);
    void run_backward_labeling(const std::vector<double>& duals);
    // 检查两个标签能否合并
    bool check_merge(const Label& fwd, const Label& bwd);
    // [注意] 需要传入 duals 计算 Reduced Cost
    std::vector<std::vector<int>> merge_and_collect(const std::vector<double>& duals);
};

#endif