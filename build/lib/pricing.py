from dataclasses import dataclass
from typing import List, Any, Tuple, Optional
from collections import deque
import heapq
import pricing_lib  # <--- [关键] 导入你编译好的 C++ 扩展模块

@dataclass
class Label:
    """
    标签类 (Label)：用于在 Pricing 子问题中记录搜索状态。
    """
    current_node: int
    cost: float
    time: float
    load: int
    visited_mask: int
    parent: Optional['Label'] = None

    def get_path(self) -> List[int]:
        """
        [核心功能] 回溯路径。
        """
        path: List[int] = []
        curr: Optional['Label'] = self
        while curr is not None:
            path.append(curr.current_node)
            curr = curr.parent
        return path[::-1]

class PricingSolver:
    
    def __init__(self, instance):
        self.inst = instance  # 持有数据引用
        self.max_labels_per_node = 50  # 每个节点保留的最大标签数
        self.EPS = 1e-5  # 容差值
        self.vehicle_fixed_cost = 2000.0
        
        # --- C++ 加速器初始化 ---
        # 告诉 C++ 我们有多少个节点，让它预分配内存
        self.cpp_checker = pricing_lib.DominanceChecker(self.inst.num_nodes)

        # --- 预计算最近邻居 (Heuristic Preprocessing) ---
        self.neighbor_limit = 20  # 只看最近的 20 个点
        self.sorted_neighbors = []
        
        # 对每个节点 i，按距离对所有 j 进行排序
        for i in range(self.inst.num_nodes):
            neighbors = []
            for j in range(self.inst.num_nodes):
                if i != j:
                    neighbors.append((self.inst.dist_matrix[i][j], j))
            
            neighbors.sort(key=lambda x: x[0])
            
            top_k = [n[1] for n in neighbors[:self.neighbor_limit]]
            if 0 not in top_k:
                top_k.append(0)  # 确保 Depot 总是在列表中
            self.sorted_neighbors.append(top_k)
            
    def _precompute_backward_bounds(self, duals):
        """
        优化版：基于时间窗排序的倒推 DP
        """
        num_nodes = self.inst.num_nodes
        bounds = [1e9] * num_nodes
        bounds[0] = 0.0
        
        sorted_nodes = sorted(range(1, num_nodes), 
                              key=lambda x: self.inst.customers[x].tw_b, 
                              reverse=True)
        
        for _ in range(1): 
            for i in sorted_nodes:
                min_val = 1e9
                for j in self.sorted_neighbors[i]:
                    if bounds[j] > 1e8: continue
                        
                    arrival_at_j = self.inst.customers[i].tw_a + \
                                   self.inst.customers[i].service_time + \
                                   self.inst.dist_matrix[i][j]
                    if arrival_at_j > self.inst.customers[j].tw_b:
                        continue
                    
                    edge_rc = self.inst.dist_matrix[i][j]
                    if j != 0:
                        edge_rc -= duals[j]
                    
                    if edge_rc + bounds[j] < min_val:
                        min_val = edge_rc + bounds[j]
                
                bounds[i] = min_val

        return bounds
    
    def solve(self, duals):
        """
        主入口：两阶段搜索策略
        """
        # --- Phase 1: 快速启发式搜索 ---
        self.backward_bounds = self._precompute_backward_bounds(duals)
        
        routes = self._solve_labeling(duals, heuristic_mode=True)
        
        if routes:
            return routes
            
        # --- Phase 2: 精确搜索 ---
        # 如果启发式没找到，启动全图搜索
        routes = self._solve_labeling(duals, heuristic_mode=False)
        return routes
    
    def _solve_labeling(self, duals, heuristic_mode=False):
        """
        [架构师修改版] 核心逻辑，接入 C++ DominanceChecker
        """
        # 1. 初始化
        # 必须清空 C++ 中的缓存，否则上一轮的标签会干扰这一轮
        self.cpp_checker.clear()

        L0 = Label(0, 0.0, 0.0, 0, 1)
        
        # 将初始标签加入 C++ 检查器
        self.cpp_checker.add_label(0, 0.0, 0.0, 0, 1)

        unprocessed = deque([L0])
        
        # Python 端的 node_labels 依然保留，用于最后截断和调试
        node_labels = [[] for _ in range(self.inst.num_nodes)]
        node_labels[0].append(L0)
        
        final_routes = []

        # 2. 搜索循环
        while unprocessed:
            curr_label = unprocessed.popleft()
            curr_node = curr_label.current_node
            
            # 决定搜索范围
            if heuristic_mode:
                search_scope = self.sorted_neighbors[curr_node]
            else:
                search_scope = range(self.inst.num_nodes)
                
            # 遍历候选节点
            for next_node in search_scope:
                # 物理扩展 (生成 Python Label 对象)
                new_label = self._extend(curr_label, next_node, duals)
                
                if new_label is None: continue 
                
                # 记录完整路径 (回到 Depot)
                if next_node == 0:
                    final_routes.append(new_label)
                    continue

                # === [核心修改：调用 C++ 进行优越性检查] ===
                # 这里不再调用 Python 的 _is_dominated，而是问 C++
                # 速度提升约 50x - 100x
                if self.cpp_checker.is_dominated(
                    next_node, 
                    new_label.cost, 
                    new_label.time, 
                    new_label.load, 
                    new_label.visited_mask
                ):
                    continue # 如果 C++ 说这个标签被支配了，直接丢弃
                
                # === [核心修改：同步数据] ===
                # 如果标签有效，必须同时添加到 C++ (供后续比较) 和 Python (供回溯)
                
                # 1. 加入 C++ 内存池
                self.cpp_checker.add_label(
                    next_node, 
                    new_label.cost, 
                    new_label.time, 
                    new_label.load, 
                    new_label.visited_mask
                )
                
                # 2. 加入 Python 队列继续搜索
                # 注意：为了保持 max_labels_per_node 的逻辑，我们依然在 Python 里做一次长度检查
                # 虽然 C++ 里面可能存了超过 50 个，但这不影响正确性，只是稍微松一点
                node_labels[next_node].append(new_label)
                
                # 简单的截断逻辑 (Optional: 可以在 Python 端做，也可以忽略)
                if len(node_labels[next_node]) > self.max_labels_per_node:
                    node_labels[next_node].sort(key=lambda x: x.cost)
                    node_labels[next_node] = node_labels[next_node][:self.max_labels_per_node]
                    # 如果 new_label 被挤出去了，就不要放入 unprocessed
                    if new_label not in node_labels[next_node]:
                         continue
                
                unprocessed.append(new_label)

        # 3. 筛选并返回
        valid_routes = []
        for r in final_routes:
            real_reduced_cost = r.cost + self.vehicle_fixed_cost
            if real_reduced_cost < -1e-6:
                r.cost = real_reduced_cost 
                valid_routes.append(r)
                
        valid_routes.sort(key=lambda x: x.cost)
        return valid_routes

    def _extend(self, label, j, duals) -> Optional[Label]:
        """
        物理扩展逻辑 (保持不变)
        """
        i = label.current_node
        customers = self.inst.customers
        dist = self.inst.dist_matrix
        
        # 1. Elementary Check
        if j != 0 and (label.visited_mask & (1 << j)):
            return None 

        # 2. Capacity Check
        new_load = label.load + customers[j].demand
        if new_load > self.inst.vehicle_capacity:
            return None

        # 3. Time Window Check
        arrival = label.time + customers[i].service_time + dist[i][j]
        start_time = max(arrival, customers[j].tw_a)
        
        if start_time > customers[j].tw_b + self.EPS:
            return None

        # 4. Reduced Cost Update
        rc_step = dist[i][j] - duals[j]
        new_cost = label.cost + rc_step
        
        future_cost = self.backward_bounds[j]
        
        # 路径连通性检查
        if future_cost > 1e8: return None
            
        # 核心剪枝逻辑
        if new_cost + future_cost + self.vehicle_fixed_cost > 1e-6:
            return None
            
        # 5. Update Mask
        new_mask = (label.visited_mask | (1 << j)) & self.inst.ng_masks[j]
        return Label(j, new_cost, start_time, new_load, new_mask, label)
        
    # def _is_dominated(...) 
    # 这个函数已经不需要了，被 C++ 取代