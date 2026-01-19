#include "pricing_engine.h"

// =======================
// 构造函数
// =======================
LabelingSolver::LabelingSolver(ProblemData p_data, double p_bucket_step) 
    : data(p_data), bucket_step(p_bucket_step) {
    
    double max_horizon = 0;
    for(double t : data.tw_end) max_horizon = std::max(max_horizon, t);
    int num_buckets = (int)(max_horizon / bucket_step) + 10;
    
    buckets.resize(num_buckets);
    dominance_sets.resize(data.num_nodes);
    label_pool.reserve(500000); // 预分配大量空间，减少 resize
    // [新增] 构建静态图
    // 这会在 C++ 侧初始化时只运行一次，极大节省后续多次 solve 的时间
    graph.build(data); 
    // === 新增：初始化 ng_masks ===
    // 将 Python 传来的 int 列表转换为 FastBitset
    data.ng_masks.resize(data.num_nodes);
    for (int i = 0; i < data.num_nodes; ++i) {
        // 如果 Python 没传数据，默认全集 (退化为基本路径 ESPPRC)
        if (data.ng_neighbor_lists.empty()) {
            for(int k=0; k<256; ++k) data.ng_masks[i].set(k); 
        } else {
            // 设置 ng-集 中的位
            for (int neighbor_idx : data.ng_neighbor_lists[i]) {
                data.ng_masks[i].set(neighbor_idx);
            }
            // 必须包含自己 (自己总是被记住的)
            data.ng_masks[i].set(i);
        }
    }
}

// =======================
// 核心：双向支配 (Bi-directional Dominance)
// =======================
bool LabelingSolver::check_and_update_dominance(int node, const Label& new_label) {
    std::vector<int>& set = dominance_sets[node];
    
    // 1. Forward Check: 新 Label 是否被旧 Label 支配？
    // 如果被支配，直接返回 true，新 Label 死亡
    for (int idx : set) {
        const Label& old = label_pool[idx];
        if (!old.active) continue;

        if (old.cost <= new_label.cost + 1e-6 &&
            old.time <= new_label.time + 1e-6 &&
            old.load <= new_label.load &&
            old.visited_mask.is_subset_of(new_label.visited_mask)) {
            return true; 
        }
    }

    // 2. Backward Check: 新 Label 是否支配旧 Label？
    // 如果支配，将旧 Label 标记为 active = false (逻辑删除)
    // 这是 C101 这种密集图能跑得动的关键！
    for (int idx : set) {
        Label& old = label_pool[idx];
        if (!old.active) continue;

        if (new_label.cost <= old.cost + 1e-6 &&
            new_label.time <= old.time + 1e-6 &&
            new_label.load <= old.load &&
            new_label.visited_mask.is_subset_of(old.visited_mask)) {
            old.active = false; // 杀掉旧 Label
        }
    }

    return false; // 新 Label 存活
}

// [新增] 构建图：预计算 + 强剪枝
void BucketGraph::build(const ProblemData& data) {
    nodes_outgoing_arcs.resize(data.num_nodes);

    for (int i = 0; i < data.num_nodes; ++i) {
        // 预分配内存，避免 push_back 导致的重分配（假设平均每个点 20-50 个邻居）
        nodes_outgoing_arcs[i].reserve(data.num_nodes / 2); 

        // 遍历所有可能的邻居（这里用原始数据中的全连接或近邻表）
        // 如果你的 data.neighbors 已经是近邻表，就在此基础上过滤
        const auto& candidates = data.neighbors[i]; // 或者 0..num_nodes

        for (int j : candidates) {
            if (i == j) continue;

            // --- 静态剪枝 (Static Pruning) ---
            
            // 1. 容量剪枝 (Capacity Cut)
            if (data.demands[i] + data.demands[j] > data.vehicle_capacity) continue;

            // 2. 时间窗剪枝 (Time Window Cut)
            // 最早到达 j 的时间 = max(TW_start[i], arrival_at_i) + service[i] + travel[i][j]
            // 这里我们用最宽松的条件：i 的最早出发时间 + 路程
            double min_arrival = data.tw_start[i] + data.service_times[i] + data.time_matrix[i][j];
            if (min_arrival > data.tw_end[j]) continue;

            // --- 构建弧 (Arc) ---
            Arc arc;
            arc.target = j;
            // 注意：Reduced Cost 依赖 Duals，是动态的，所以这里只存静态的距离成本
            // 在 solve 中我们再减去 duals[j]
            arc.cost = data.dist_matrix[i][j]; 
            // 预计算 duration = travel + service_at_i (注意定义的语义)
            // 通常 label.time 是到达时间。到达 j = 到达 i + service_at_i + travel
            arc.duration = data.service_times[i] + data.time_matrix[i][j];
            arc.distance = data.dist_matrix[i][j];
            arc.demand = data.demands[j];

            nodes_outgoing_arcs[i].push_back(arc);
        }
    }
}

// =======================
// 主求解逻辑
// =======================
std::vector<std::vector<int>> LabelingSolver::solve(const std::vector<double>& duals) {
    // 1. 重置
    label_pool.clear();
    for(auto& vec : dominance_sets) vec.clear();
    for(auto& vec : buckets) vec.clear();

    // 2. 初始化 Root Label (Depot)
    Label root;
    root.node_id = 0;
    root.parent_index = -1;
    root.cost = 0.0;
    root.time = data.tw_start[0];
    root.load = 0;
    root.visited_mask.set(0); 
    root.active = true;

    label_pool.push_back(root);
    buckets[0].push_back(0);
    dominance_sets[0].push_back(0);

    // 3. Bucket 循环
    for (int b = 0; b < buckets.size(); ++b) {
        // 使用索引遍历，因为 buckets[b] 可能在循环中不被修改，
        // 但为了安全和性能，最好将本轮要处理的全部取出来，或者标准索引遍历
        // 注意：Labeling 算法中，推入的桶索引通常 >= 当前桶，所以当前桶不会增加元素
        const auto& current_bucket_indices = buckets[b];
        
        for (int curr_idx : current_bucket_indices) {
            // 引用检查，必须用引用获取 active 状态，但拷贝数据用于计算
            if (!label_pool[curr_idx].active) continue;
            
            // 拷贝一份数据到栈上，避免 label_pool 扩容导致引用失效
            const Label curr_label = label_pool[curr_idx]; 

            int i = curr_label.node_id;
            // [修改] 使用 BucketGraph 的预处理弧进行遍历
            // 这里的 arcs 已经是经过“容量”和“静态时间窗”过滤的
            const auto& arcs = graph.nodes_outgoing_arcs[i];
            for (const auto& arc : arcs) {
                int j = arc.target;

                // a. ng-Route 可行性检查 (保持不变)
                if (curr_label.visited_mask.test(j)) continue;

                // b. 资源检查 (简化版)
                // 静态容量已经在 build 时检查过了，但在 Labeling 中累积容量仍需检查
                int new_load = curr_label.load + arc.demand;
                if (new_load > data.vehicle_capacity) continue;

                // 时间计算：直接使用预计算的 duration
                double arrival = curr_label.time + arc.duration;
                double start_time = std::max(arrival, data.tw_start[j]);

                // [关键] 此时再做一次动态时间窗检查
                // 虽然 build 时做了检查，但那是基于 i 的最早时间。
                // 现在的 curr_label.time 可能比最早时间晚，所以必须检查。
                if (start_time > data.tw_end[j]) continue;

                // c. 计算 Cost (结合 Duals)
                // Reduced Cost = arc.cost (distance) - duals[j]
                double rc = arc.cost - duals[j];
                double new_cost = curr_label.cost + rc;
                
                // d. 构造新掩码 (ng-relaxation 核心)
                // NewMask = (OldMask & ng_mask[j]) | {j}
                FastBitset new_mask = curr_label.visited_mask.apply_ng_relaxation(data.ng_masks[j], j);

                // e. 构造临时 Label 用于支配性检查
                Label temp_label;
                temp_label.cost = new_cost;
                temp_label.time = start_time;
                temp_label.load = new_load;
                temp_label.visited_mask = new_mask;
                // node_id 和 parent 不需要参与支配检查

                // f. 支配性检查 (Check + Clean)
                if (check_and_update_dominance(j, temp_label)) {
                    continue; // 被支配，跳过
                }

                // g. 添加新 Label
                temp_label.node_id = j;
                temp_label.parent_index = curr_idx;
                temp_label.active = true;

                int new_idx = (int)label_pool.size();
                label_pool.push_back(temp_label);
                
                // 加入支配集
                dominance_sets[j].push_back(new_idx);

                // 加入时间桶
                int bucket_idx = (int)(start_time / bucket_step);
                if (bucket_idx < buckets.size()) {
                    buckets[bucket_idx].push_back(new_idx);
                }
            }
        }
    }

    // =======================
    // 4. 收集结果 (回到 Depot)
    // =======================
    std::vector<std::pair<double, int>> best_labels;
    
    // 遍历所有非 Depot 点
    for(int i=1; i<data.num_nodes; ++i) {
        for(int idx : dominance_sets[i]) {
            const Label& L = label_pool[idx];
            if (!L.active) continue;

            double arrival_depot = L.time + data.service_times[i] + data.time_matrix[i][0];
            if (arrival_depot <= data.tw_end[0]) {
                double final_cost = L.cost + data.dist_matrix[i][0] - duals[0];
                if (final_cost < -1e-5) {
                    best_labels.push_back({final_cost, idx});
                }
            }
        }
    }

    std::sort(best_labels.begin(), best_labels.end());
    
    // 限制返回路径数量 (Heuristic limit)
    int limit = std::min((int)best_labels.size(), 50);
    std::vector<std::vector<int>> results;

    for(int k=0; k<limit; ++k) {
        int idx = best_labels[k].second;
        std::vector<int> path;
        path.push_back(0);
        
        int curr = idx;
        while(curr != -1) {
            path.push_back(label_pool[curr].node_id);
            curr = label_pool[curr].parent_index;
        }
        std::reverse(path.begin(), path.end());
        results.push_back(path);
    }

    return results;
}