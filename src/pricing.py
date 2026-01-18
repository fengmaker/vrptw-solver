from dataclasses import dataclass
from typing import List, Any, Tuple, Optional
from collections import deque
import heapq
@dataclass
class Label:
    """
    标签类 (Label)：用于在 Pricing 子问题中记录搜索状态。
    这就好比是一个探险者的'日记本'，记录了走到当前这一步的所有信息。
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
        从当前标签开始，顺着 'parent' 指针一直往回找，直到找到起点 (Depot)。
        
        Returns:
            List[int]: 完整的路径节点列表，例如 [0, 5, 2, 0]
                       (顺序：从 Depot 出发 -> ... -> 回到 Depot)
        """
        path: List[int] = []
        curr: Optional['Label'] = self  # 1. 从当前标签开始 (通常是终点 Depot 的标签)
        while curr is not None:          # 2. 只要还有父亲，就一直往回追溯
            path.append(curr.current_node)
            curr = curr.parent
        return path[::-1] # 3. 反转列表 因为我们是从 终点 -> 起点 追溯的，记录的是 [0, 2, 5, 0] 我们需要返回 [0, 5, 2, 0]

class PricingSolver:
    
    def __init__(self, instance):
        self.inst = instance  # 持有数据引用
        self.max_labels_per_node = 50  # 每个节点保留的最大标签数
        self.EPS = 1e-5  # <--- 新增：容差值
        self.vehicle_fixed_cost = 2000.0
        # --- 新增：预计算最近邻居 (Heuristic Preprocessing) ---
        self.neighbor_limit = 20  # 只看最近的 20 个点
        self.sorted_neighbors = []
        
        # 对每个节点 i，按距离对所有 j 进行排序
        for i in range(self.inst.num_nodes):
            # 创建 (distance, node_index) 的列表，跳过自己
            neighbors = []
            for j in range(self.inst.num_nodes):
                if i != j:
                    neighbors.append((self.inst.dist_matrix[i][j], j))
            
            # 按距离从小到大排序
            neighbors.sort(key=lambda x: x[0])
            
            # 只取前 K 个的索引
            # 注意：Depot(0) 不一定在最近邻居里，但在搜索时我们会单独处理它
            top_k = [n[1] for n in neighbors[:self.neighbor_limit]]
            if 0 not in top_k:
                top_k.append(0)  # 确保 Depot 总是在列表中
            self.sorted_neighbors.append(top_k)
            
    def _precompute_backward_bounds(self, duals):
        """
        优化版：基于时间窗排序的倒推 DP (Label Setting 思想)
        复杂度：O(N * K)，其中 K 是邻居数量。速度极快。
        """
        num_nodes = self.inst.num_nodes
        # bounds[i] 表示：从节点 i 回到 Depot (节点0) 的最小 Reduced Cost 下界
        bounds = [1e9] * num_nodes
        bounds[0] = 0.0  # Depot 回家代价为 0
        
        # 1. 按照时间窗右端点 (Latest Arrival Time) 对节点进行降序排序
        # 逻辑：晚关门的店通常是路径靠后的点，我们从后往前推
        # 排除 Depot(0)，只排客户点
        sorted_nodes = sorted(range(1, num_nodes), 
                              key=lambda x: self.inst.customers[x].tw_b, 
                              reverse=True)
        
        # 2. 动态规划迭代
        # 为了处理时间窗重叠的情况，我们可以跑 1-2 遍 Relaxation，通常 1 遍对于 Bound 足够了
        # 如果追求更紧的 Bound，可以把 range(1) 改成 range(2)
        for _ in range(1): 
            for i in sorted_nodes:
                min_val = 1e9
                
                # 只查看预处理过的最近邻居 (self.sorted_neighbors)
                # 这避免了对全图 O(N^2) 的扫描
                for j in self.sorted_neighbors[i]:
                    
                    # 剪枝：如果 j 的状态还没算出来（还是初始极大值），跳过
                    if bounds[j] > 1e8:
                        continue
                        
                    # 基础可行性检查 (时间窗)
                    # 如果 i 最早出发都赶不上 j 的最晚关门，那 i->j 物理不可行
                    # (这步检查非常重要，能剔除很多无效边)
                    arrival_at_j = self.inst.customers[i].tw_a + \
                                   self.inst.customers[i].service_time + \
                                   self.inst.dist_matrix[i][j]
                    if arrival_at_j > self.inst.customers[j].tw_b:
                        continue
                    
                    # 计算边权 (Reduced Cost)
                    # cost(i->j) = dist[i][j] - duals[j]
                    # 注意：Depot (j=0) 没有 dual，或者 dual=0
                    edge_rc = self.inst.dist_matrix[i][j]
                    if j != 0:
                        edge_rc -= duals[j]
                    
                    # 状态转移
                    if edge_rc + bounds[j] < min_val:
                        min_val = edge_rc + bounds[j]
                
                bounds[i] = min_val

        return bounds
    
    def solve(self, duals):
        """
        新的主入口：两阶段搜索策略
        """
        # --- Phase 1: 快速启发式搜索 (Heuristic Search) ---
        # 只搜索最近邻居，速度极快
        self.backward_bounds = self._precompute_backward_bounds(duals)
        
        routes = self._solve_labeling(duals, heuristic_mode=True)
        
        # 如果启发式找到了负 RC 的路径，直接交卷！(贪婪策略)
        if routes:
            return routes
            
        # --- Phase 2: 精确搜索 (Exact Search) ---
        # 如果启发式没找到（说明现在的 Duals 很刁钻），无奈启动全图搜索
        # print("  [Pricing] Heuristic failed. Switching to Exact Search...")
        routes = self._solve_labeling(duals, heuristic_mode=False)
        return routes
    
   
    def _solve_labeling(self, duals, heuristic_mode=False):
        """
        原 solve 函数的核心逻辑，增加了 heuristic_mode 开关
        """
        # 1. 初始化
        L0 = Label(0, 0.0, 0.0, 0, 1)
        unprocessed = deque([L0])
        node_labels = [[] for _ in range(self.inst.num_nodes)]
        node_labels[0].append(L0)
        
        final_routes = []

        # 2. 搜索循环
        while unprocessed:
            curr_label = unprocessed.popleft()
            curr_node = curr_label.current_node
            
            # --- 核心修改：决定搜索范围 ---
            if heuristic_mode:
                # 模式 A: 只看“朋友圈”
                search_scope = self.sorted_neighbors[curr_node]
            else:
                # 模式 B: 遍历全图 (0 到 N)
                search_scope = range(self.inst.num_nodes)
                
            # 遍历候选节点
            for next_node in search_scope:
                # 物理扩展 (调用之前的函数)
                new_label = self._extend(curr_label, next_node, duals)
                
                if new_label is None: continue 
                
                # 记录完整路径 (next_node == 0)
                if next_node == 0:
                    final_routes.append(new_label)
                    continue

                # 支配性检查
                if self._is_dominated(new_label, node_labels[next_node]):
                    continue
                
                # 保存并截断
                node_labels[next_node].append(new_label)
                if len(node_labels[next_node]) > self.max_labels_per_node:
                    node_labels[next_node].sort(key=lambda x: x.cost)
                    node_labels[next_node] = node_labels[next_node][:self.max_labels_per_node]
                    if new_label not in node_labels[next_node]:
                         continue
                
                unprocessed.append(new_label)

        # 3. 筛选并返回 (逻辑不变)
        valid_routes = []
        for r in final_routes:
            real_reduced_cost = r.cost + self.vehicle_fixed_cost
            if real_reduced_cost < -1e-6:
                r.cost = real_reduced_cost 
                valid_routes.append(r)
                
        valid_routes.sort(key=lambda x: x.cost)
        return valid_routes

    def _extend(self, label, j, duals) -> Optional[Label]:
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
        
        if start_time > customers[j].tw_b + self.EPS: # 允许微小容差
            return None

        # 4. Reduced Cost Update
        # RC = Old_RC + (Dist_ij - Dual_j)
        rc_step = dist[i][j] - duals[j]
        new_cost = label.cost + rc_step
        
        # potential_total_rc = new_cost + self.backward_bounds[j]
        
        # # 如果就算后面走得最好，总 Reduced Cost 也是正的，那就别走了
        # # (加个 self.EPS 防止浮点误差吃掉 0)
        # if potential_total_rc > -1e-6: 
        #      return None
        future_cost = self.backward_bounds[j]
        
        # 路径连通性检查
        if future_cost > 1e8: return None
            
        # 核心剪枝逻辑
        # 我们需要: (new_cost + future_cost + fixed_cost) < 0
        # 所以如果: (new_cost + future_cost + fixed_cost) > EPS，则剪枝
        if new_cost + future_cost + self.vehicle_fixed_cost > 1e-6:
            return None
        # 5. Update Mask
        # new_mask = label.visited_mask | (1 << j)
        new_mask = (label.visited_mask | (1 << j)) & self.inst.ng_masks[j]
        return Label(j, new_cost, start_time, new_load, new_mask, label)
        
    def _is_dominated(self, new, existing_labels) -> bool:
        for old in existing_labels:
            if (old.cost <= new.cost + self.EPS and
                old.time <= new.time + self.EPS and
                old.load <= new.load and
                (old.visited_mask & new.visited_mask) == old.visited_mask):
                return True
        return False