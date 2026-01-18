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
            
            // 遍历邻居
            for (int j : data.neighbors[i]) {
                // a. ng-Route 可行性检查
                // 检查 j 是否在当前的 ng-relaxed mask 中
                // 如果在 mask 中，说明 j 之前访问过，且属于 j 自己的“记忆集”，不能再访问
                if (curr_label.visited_mask.test(j)) continue;

                // b. 资源检查
                int new_load = curr_label.load + data.demands[j];
                if (new_load > data.vehicle_capacity) continue;

                double travel_time = data.time_matrix[i][j];
                double arrival = curr_label.time + data.service_times[i] + travel_time;
                double start_time = std::max(arrival, data.tw_start[j]);

                if (start_time > data.tw_end[j]) continue;

                // c. 计算 Cost
                double rc = data.dist_matrix[i][j] - duals[j]; // Reduced Cost
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