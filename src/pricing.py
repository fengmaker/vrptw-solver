from dataclasses import dataclass
from typing import List, Tuple
import pricing_lib  # <--- 导入编译好的 C++ 扩展模块

@dataclass
class Route:
    """
    用于返回给主问题的数据结构
    """
    path: List[int]
    cost: float       # <--- [修改] 统一命名为 cost (对应 Reduced Cost)
    real_cost: float  # 真实路程成本 (用于计算目标函数)
    def get_path(self) -> List[int]:
        return self.path
    
class PricingSolver:
    def __init__(self, instance):
        self.inst = instance
        # 请根据你的模型确认：固定成本是在这里加，还是在主问题 Duals 里处理
        # 如果主问题的 Duals 包含了 convexity constraint 的 dual (比如 duals[0]), 
        # 且该约束对应车辆数限制，那么 vehicle_fixed_cost 可能不需要在这里重复加。
        # 这里保留原本逻辑。
        self.vehicle_fixed_cost = 2000.0
        
        # =========================================
        # 1. 数据转换 (Python Object -> C++ Struct)
        # =========================================
        cpp_data = pricing_lib.ProblemData()
        cpp_data.num_nodes = instance.num_nodes
        cpp_data.vehicle_capacity = instance.vehicle_capacity
        
        # 提取数据 (C++ vector <-> Python List)
        cpp_data.demands = [c.demand for c in instance.customers]
        cpp_data.service_times = [c.service_time for c in instance.customers]
        cpp_data.tw_start = [c.tw_a for c in instance.customers]
        cpp_data.tw_end = [c.tw_b for c in instance.customers]
        
        # 提取矩阵
        cpp_data.dist_matrix = instance.dist_matrix
        # 兼容性处理：如果没有 time_matrix，复用 dist_matrix
        cpp_data.time_matrix = getattr(instance, 'time_matrix', instance.dist_matrix)
        ng_size = 10 
        ng_lists = []

        for i in range(instance.num_nodes):
            # 拿到所有点到 i 的距离：(dist, node_index)
            dists = []
            for j in range(instance.num_nodes):
                dists.append((instance.dist_matrix[i][j], j))
            
            # 按距离排序
            dists.sort(key=lambda x: x[0])
            
            # 取最近的 ng_size 个点的索引
            # 注意：这定义了“当我们到达 i 时，我们需要记住哪些点被访问过”
            # 通常包含离 i 最近的那些点。
            neighbors = [x[1] for x in dists[:ng_size]]
            
            # 确保包含 0 (Depot)，虽然通常逻辑包含，但显式加上更安全
            if 0 not in neighbors:
                neighbors.append(0)
                
            ng_lists.append(neighbors)

        # 3. 传给 C++
        # Pybind11 会自动把 List[List[int]] 转成 std::vector<std::vector<int>>
        cpp_data.ng_neighbor_lists = ng_lists
        # =========================================
        # 2. 预处理邻居列表 (Heuristic Preprocessing)
        # =========================================
        neighbor_limit = 20  # <--- [修改] 设大一点，或者干脆对 R101 不做截断
        cpp_neighbors = []
        
        for i in range(instance.num_nodes):
            all_neighbors = []
            for j in range(instance.num_nodes):
                if i == j: continue
                
                # [可选] 简单的时间窗剪枝
                # 如果从 i 出发，即便全速赶路也无法在 j 的截止时间前到达，则断开连接
                dist = instance.dist_matrix[i][j]
                arrival_time = instance.customers[i].tw_a + instance.customers[i].service_time + dist
                if arrival_time > instance.customers[j].tw_b:
                    continue
                    
                all_neighbors.append((dist, j))
            
            # 按距离排序
            all_neighbors.sort(key=lambda x: x[0])
            
            # [核心修复]
            # 如果是 Depot (0)，必须连接所有可行点，确保每个客户都能作为路径的起点！
            # 如果是普通点，可以截断以加速
            if i == 0:
                sorted_indices = [x[1] for x in all_neighbors] # Depot 全连接
            else:
                sorted_indices = [x[1] for x in all_neighbors[:neighbor_limit]]
            
            # 确保回程可行：每个点的邻居里最好都包含 0
            # (虽然 C++ 代码逻辑里通常是单独处理回 Depot 的，但加进去也没坏处)
            if 0 not in sorted_indices:
                sorted_indices.append(0)
            
            cpp_neighbors.append(sorted_indices)
            
        cpp_data.neighbors = cpp_neighbors

        # =========================================
        # 3. 初始化 C++ 求解器
        # =========================================
        # Bucket Step: 建议设为平均旅行时间的一半，例如 10.0
        self.cpp_solver = pricing_lib.LabelingSolver(cpp_data, 10.0)

    def solve(self, duals: List[float]) -> List[Route]:
        """
        调用 C++ 引擎求解
        """
        # 1. C++ 求解 (返回 List[List[int]])
        raw_paths = self.cpp_solver.solve(duals)
        
        results = []
        
        # 2. 后处理
        for path in raw_paths:
            # 计算成本
            r_cost, real_c = self._calculate_path_costs(path, duals)
            
            # 双重检查负 Reduced Cost
            if r_cost < -1e-5:
                # [修改] 这里实例化 Route 时使用 cost 参数
                results.append(Route(path=path, cost=r_cost, real_cost=real_c))
                
        return results

    def _calculate_path_costs(self, path: List[int], duals: List[float]) -> Tuple[float, float]:
        """
        计算 Reduced Cost 和 Real Cost
        """
        real_cost = 0.0
        reduced_cost = 0.0
        
        # 加上固定成本
        reduced_cost += self.vehicle_fixed_cost 
        
        curr = path[0]
        for next_node in path[1:]:
            dist = self.inst.dist_matrix[curr][next_node]
            real_cost += dist
            
            # Reduced Cost 公式: c_ij - dual_j
            rc_step = dist
            if next_node != 0: 
                # 注意：对偶变量通常对应客户约束 (index 1..N)
                # 需确保 duals 列表长度正确且索引对齐
                if next_node < len(duals):
                    rc_step -= duals[next_node]
            
            reduced_cost += rc_step
            curr = next_node
            
        return reduced_cost, real_cost