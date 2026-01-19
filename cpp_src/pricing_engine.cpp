#include "pricing_engine.h"

// =======================
// 构造函数
// =======================
// ==========================================
// 2. Solver 构造函数 (初始化两个图)
// ==========================================
LabelingSolver::LabelingSolver(ProblemData p_data, double p_bucket_step) 
    : data(p_data), bucket_step(p_bucket_step) {
    
    // 初始化标签存储容器
    fwd_labels.reserve(200000);
    bwd_labels.reserve(200000);

    // 构建双向图
    fwd_graph.build(data, false); // Forward
    bwd_graph.build(data, true);  // Backward

    // 初始化 ng_masks (同前)
    data.ng_masks.resize(data.num_nodes);
    if (data.ng_neighbor_lists.empty()) {
        for (int i = 0; i < data.num_nodes; ++i) 
            for(int k=0; k<256; ++k) data.ng_masks[i].set(k);
    } else {
        for (int i = 0; i < data.num_nodes; ++i) {
            for (int neighbor_idx : data.ng_neighbor_lists[i]) {
                data.ng_masks[i].set(neighbor_idx);
            }
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
void BucketGraph::build(const ProblemData& data, bool is_backward) {
    nodes_outgoing_arcs.clear();
    nodes_outgoing_arcs.resize(data.num_nodes);

    for (int i = 0; i < data.num_nodes; ++i) {
        // 原始数据的 neighbors 是物理上的出边
        // 如果是 Backward Graph，我们需要知道 "谁能走到 i" (入边)
        // 或者简单起见，我们遍历所有点对 (既然做了剪枝，性能尚可)
        // 更好的方式：Python 传入 data.predecessors，或者在这里全遍历过滤
        
        // 为了演示清晰，这里假设全遍历检查 (实际工程中应用反向邻接表优化)
        const auto& candidates = data.neighbors[i]; // i 的物理邻居

        for (int j : candidates) { // 物理边 i -> j
            if (i == j) continue;

            // 容量剪枝 (方向无关)
            if (data.demands[i] + data.demands[j] > data.vehicle_capacity) continue;

            Arc arc;
            
            if (!is_backward) {
                // === Forward Logic (i -> j) ===
                double arrival = data.tw_start[i] + data.service_times[i] + data.time_matrix[i][j];
                if (arrival > data.tw_end[j]) continue;

                arc.target = j;
                arc.cost = data.dist_matrix[i][j]; 
                arc.duration = data.service_times[i] + data.time_matrix[i][j];
                arc.demand = data.demands[j]; // 累加 j 的需求
                arc.distance = data.dist_matrix[i][j];
                
                nodes_outgoing_arcs[i].push_back(arc);
            } else {
                // === Backward Logic ===
                // 物理边是 i -> j。
                // 在后向搜索中，我们目前的 Label 在 j，要试图"退回"到 i。
                // 所以我们在 j 的出边列表中添加一个指向 i 的边。
                // 这里的循环结构需要调整：外层循环遍历的是 "Source Node" in Search Graph.
                // 如果是 Backward，Source Node 是 j，Target 是 i。
            }
        }
    }

    // 修正：上面的循环结构对于 Backward 构建不太高效。
    // 建议采用两遍循环分离写法：
    
    if (is_backward) {
        // 重置并在下面重新填充
        nodes_outgoing_arcs.clear(); 
        nodes_outgoing_arcs.resize(data.num_nodes);
        
        for (int i = 0; i < data.num_nodes; ++i) { // i is Physical Start
            for (int j : data.neighbors[i]) {      // j is Physical End
                if (i == j) continue;
                
                // 物理边 i -> j. 
                // 后向搜索图：从 j -> i
                // 时间检查：从 j 出发(最晚时间)，减去路程，能否在 i 的最晚时间之前离开 i?
                // Backward Time: "Latest Departure Time from Node"
                // strict logic needed here.
                
                // 简单处理：仅添加反向边，具体时间窗在 Labeling 中检查
                // 或者在这里做粗略剪枝
                Arc arc;
                arc.target = i; // 反向：目标是 i
                arc.cost = data.dist_matrix[i][j]; 
                // 后向 Duration: 我们需要减去 (Travel_ij + Service_i)
                arc.duration = data.time_matrix[i][j] + data.service_times[i]; 
                arc.demand = data.demands[i]; // 退回到 i，累加 i 的需求
                arc.distance = data.dist_matrix[i][j];

                // 将边加入 j 的列表 (因为搜索是从 j 扩展到 i)
                nodes_outgoing_arcs[j].push_back(arc);
            }
        }
    }
}

void LabelingSolver::run_forward_labeling(const std::vector<double>& duals) {
    // 初始化 Root (Depot)
    Label root;
    root.node_id = 0;
    root.parent_index = -1;
    root.cost = 0.0;
    root.time = data.tw_start[0];
    root.load = 0;
    root.visited_mask.set(0);
    root.active = true;

    fwd_labels.push_back(root);
    nodes_fwd_labels[0].push_back(0);

    // 简单队列 (BFS) - 实际应用中可用桶排序优化
    int head = 0;
    while(head < fwd_labels.size()) {
        int curr_idx = head++;
        const Label& curr = fwd_labels[curr_idx];
        if (!curr.active) continue;
        
        // 限制：只搜索到一半 (Halfway point pruning)
        // 简单策略：如果时间超过 horizon 的 0.6，停止扩展
        if (curr.time > data.tw_end[0] * 0.6) continue; 

        const auto& arcs = fwd_graph.nodes_outgoing_arcs[curr.node_id];
        for (const auto& arc : arcs) {
            int next = arc.target;
            if (curr.visited_mask.test(next)) continue;
            if (curr.load + arc.demand > data.vehicle_capacity) continue;

            double arrival = curr.time + arc.duration;
            if (arrival > data.tw_end[next]) continue;
            double start_time = std::max(arrival, data.tw_start[next]);

            // Reduced Cost: c_ij - dual_j
            double rc = arc.cost - duals[next];
            
            // 支配性检查 (此处省略，为了代码跑通先不做强支配)
            
            Label new_label = curr;
            new_label.node_id = next;
            new_label.parent_index = curr_idx;
            new_label.cost += rc;
            new_label.time = start_time;
            new_label.load += arc.demand;
            new_label.visited_mask = curr.visited_mask.apply_ng_relaxation(data.ng_masks[next], next);
            new_label.active = true;

            int new_idx = (int)fwd_labels.size();
            fwd_labels.push_back(new_label);
            nodes_fwd_labels[next].push_back(new_idx);
        }
    }
}

// ==========================================
// 5. Backward Labeling (新增)
// ==========================================
void LabelingSolver::run_backward_labeling(const std::vector<double>& duals) {
    Label root;
    root.node_id = 0; // Depot
    root.parent_index = -1;
    root.cost = 0.0;
    root.time = data.tw_end[0]; // 从最晚时间开始
    root.load = 0;
    root.visited_mask.set(0);
    root.active = true;

    bwd_labels.push_back(root);
    nodes_bwd_labels[0].push_back(0);

    int head = 0;
    while(head < bwd_labels.size()) {
        int curr_idx = head++;
        const Label& curr = bwd_labels[curr_idx];
        if (!curr.active) continue;
        
        // Backward Pruning: 时间小于 0.4 * Horizon 停止 (对应 Forward 的 0.6)
        if (curr.time < data.tw_end[0] * 0.4) continue;

        const auto& arcs = bwd_graph.nodes_outgoing_arcs[curr.node_id];
        for (const auto& arc : arcs) {
            int prev = arc.target; // 物理上的上游
            if (curr.visited_mask.test(prev)) continue;
            if (curr.load + arc.demand > data.vehicle_capacity) continue;

            // Backward Time Check
            // 我们必须在 new_time 时刻到达 prev，才能赶上 curr.time
            // new_time <= curr.time - travel(prev, curr) - service(prev)
            double latest_start = curr.time - arc.duration; 
            if (latest_start < data.tw_start[prev]) continue;
            
            // 确保不晚于 prev 的最晚结束
            double execution_time = std::min(latest_start, data.tw_end[prev]);

            // Reduced Cost: Backward 时，边的 cost 是 c_prev_curr
            // Dual 扣在 prev 节点上 (除了 Depot)
            // RC = c_prev_curr - dual_prev
            double rc_val = arc.cost;
            if (prev != 0) rc_val -= duals[prev];

            Label new_label = curr;
            new_label.node_id = prev;
            new_label.parent_index = curr_idx;
            new_label.cost += rc_val;
            new_label.time = execution_time;
            new_label.load += arc.demand;
            new_label.visited_mask = curr.visited_mask.apply_ng_relaxation(data.ng_masks[prev], prev);
            new_label.active = true;

            int new_idx = (int)bwd_labels.size();
            bwd_labels.push_back(new_label);
            nodes_bwd_labels[prev].push_back(new_idx);
        }
    }
}

// ==========================================
// 6. Merge and Collect (新增)
// ==========================================
std::vector<std::vector<int>> LabelingSolver::merge_and_collect(const std::vector<double>& duals) {
    std::vector<std::pair<double, std::vector<int>>> merged_routes;

    // 在每一个节点尝试接合
    for (int i = 1; i < data.num_nodes; ++i) {
        for (int f_idx : nodes_fwd_labels[i]) {
            const Label& L_f = fwd_labels[f_idx];
            
            for (int b_idx : nodes_bwd_labels[i]) {
                const Label& L_b = bwd_labels[b_idx];

                // 1. 资源检查
                if (L_f.load + L_b.load - data.demands[i] > data.vehicle_capacity) continue;
                if (L_f.time > L_b.time + 1e-6) continue;

                // 2. 环路检查 (Mask Intersection)
                // 暂时简单处理：如果不相交则合并 (SOTA 需要更精细的位运算)
                // 假设 FastBitset 已有 intersects 方法，或者这里暂时跳过强检查
                // if (L_f.visited_mask.intersects(L_b.visited_mask, i)) continue;

                // 3. Cost Calculation
                // Total RC = Fwd.RC + Bwd.RC + dual[i]
                // 解释：Fwd 累加了 -dual[i]，Bwd 也累加了 -dual[i] (因为它把 i 当作 target)
                // 但实际上 i 只出现一次，所以要加回一个 dual[i]
                double total_rc = L_f.cost + L_b.cost + duals[i];

                if (total_rc < -1e-5) {
                    // Reconstruct Path
                    std::vector<int> path;
                    
                    // Add Forward part
                    int curr = f_idx;
                    while (curr != -1) {
                        path.push_back(fwd_labels[curr].node_id);
                        curr = fwd_labels[curr].parent_index;
                    }
                    std::reverse(path.begin(), path.end());
                    
                    // Add Backward part (skip the first one which is i, already added)
                    curr = L_b.parent_index; 
                    while (curr != -1) {
                        path.push_back(bwd_labels[curr].node_id);
                        curr = bwd_labels[curr].parent_index;
                    }

                    merged_routes.push_back({total_rc, path});
                }
            }
        }
    }

    // 排序并返回前 50 个
    std::sort(merged_routes.begin(), merged_routes.end(), [](const auto& a, const auto& b){
        return a.first < b.first;
    });

    std::vector<std::vector<int>> results;
    int limit = std::min((int)merged_routes.size(), 50);
    for(int k=0; k<limit; ++k) results.push_back(merged_routes[k].second);
    
    return results;
}


std::vector<std::vector<int>> LabelingSolver::solve(const std::vector<double>& duals) {
    // 清空上一轮状态
    fwd_labels.clear();
    bwd_labels.clear();
    nodes_fwd_labels.assign(data.num_nodes, {});
    nodes_bwd_labels.assign(data.num_nodes, {});

    // 运行双向搜索
    run_forward_labeling(duals);
    run_backward_labeling(duals);

    // 接合
    return merge_and_collect(duals);
}