import pytest
import math
# 假设你的模块叫 pricing_lib (在 setup.py 中定义的)
import pricing_lib as m 

# ==========================================
# Helper: 构造测试数据的工具函数
# ==========================================
class PricingDataBuilder:
    def __init__(self, num_nodes):
        self.num_nodes = num_nodes
        self.capacity = 100
        self.demands = [0] * num_nodes
        self.service_times = [0.0] * num_nodes
        # 默认时间窗无限大
        self.tw_start = [0.0] * num_nodes
        self.tw_end = [1000.0] * num_nodes
        # 默认距离和时间矩阵 (初始化为 0 或 大数)
        self.dist_matrix = [[0.0 if i == j else 100.0 for j in range(num_nodes)] for i in range(num_nodes)]
        self.time_matrix = [[0.0 if i == j else 10.0 for j in range(num_nodes)] for i in range(num_nodes)]
        # 默认全连接
        self.neighbors = [list(range(num_nodes)) for _ in range(num_nodes)]
        # NG Sets (默认包含所有点，即 exact ESPPRC)
        self.ng_sets = [list(range(num_nodes)) for _ in range(num_nodes)]

    def set_edge(self, u, v, dist, time=None):
        self.dist_matrix[u][v] = dist
        self.time_matrix[u][v] = time if time is not None else dist

    def to_cpp_input(self):
        # 这一步取决于你的 C++ bind 怎么写的。
        # 假设你的 C++ 接受一个 ProblemData 对象，或者由 Python dict 转换
        # 这里模拟构造成 ProblemData
        p = m.ProblemData()
        p.num_nodes = self.num_nodes
        p.vehicle_capacity = self.capacity
        p.demands = self.demands
        p.service_times = self.service_times
        p.tw_start = self.tw_start
        p.tw_end = self.tw_end
        p.dist_matrix = self.dist_matrix
        p.time_matrix = self.time_matrix
        p.neighbors = self.neighbors
        p.ng_neighbor_lists = self.ng_sets
        return p

# ==========================================
# 1. 基础功能与约束测试
# ==========================================

# 修改 test_simple_shortest_path
def test_simple_shortest_path():
    b = PricingDataBuilder(2)
    b.set_edge(0, 1, 10.0)
    b.set_edge(1, 0, 10.0)
    
    # 【修改点】给 Node 1 一个巨大的奖励 (Dual = 50)
    # 路径成本: 10 + 10 = 20
    # Reduced Cost: 20 - 50 = -30 (负数！求解器会保留它)
    duals = [0.0, 50.0] 
    
    solver = m.LabelingSolver(b.to_cpp_input(), bucket_step=1.0)
    paths = solver.solve(duals)
    assert len(paths) > 0

def test_capacity_constraint():
    """
    测试容量限制
    0 -> 1 (需求 60)
    0 -> 2 (需求 60)
    1 -> 2 (距离很短)
    车辆容量 100。应该无法走 0 -> 1 -> 2 -> 0，因为 60+60 > 100
    """
    b = PricingDataBuilder(3)
    b.capacity = 100
    b.demands = [0, 60, 60]
    
    # 设置一个非常有诱惑力的三角形
    b.set_edge(0, 1, 10)
    b.set_edge(1, 2, 10) # 1->2 很近
    b.set_edge(2, 0, 10)
    
    # 设置单独往返
    b.set_edge(0, 2, 100) # 直连很远
    
    duals = [0.0] * 3
    solver = m.LabelingSolver(b.to_cpp_input(), 1.0)
    paths = solver.solve(duals)
    
    # 检查所有生成的路径，不能包含 [0, 1, 2, 0] 或 [0, 2, 1, 0]
    for path in paths:
        # 如果路径包含 1 和 2，说明容量约束失效了
        assert not (1 in path and 2 in path), f"Path {path} violates capacity constraint!"

def test_time_window_constraint():
    """
    测试时间窗
    0 -> 1 (耗时 10)
    Node 1 时间窗 [20, 30]
    """
    b = PricingDataBuilder(2)
    b.set_edge(0, 1, 10.0, time=10.0) # 到达时刻 10
    b.tw_start[1] = 20.0 # 必须等到 20 才能服务
    b.service_times[1] = 5.0 # 服务耗时 5，离开时刻 25
    b.set_edge(1, 0, 10.0, time=10.0) # 回到 depot 时刻 35
    
    b.tw_end[0] = 100.0 # Depot 关门很晚
    
    # 【修改点】同样给个奖励，确保 cost < 0
    duals = [0.0, 50.0] 
    
    solver = m.LabelingSolver(b.to_cpp_input(), 1.0)
    paths = solver.solve(duals)
    assert [0, 1, 0] in paths

# ==========================================
# 2. NG-Route 核心逻辑测试 (最重要!)
# ==========================================

def test_ng_route_cycle():
    """测试 NG-Route 允许循环的情况 (忘记机制)"""
    b = PricingDataBuilder(3)
    b.set_edge(0, 1, 10)
    b.set_edge(1, 2, 10)
    b.set_edge(2, 1, 10)
    b.set_edge(1, 0, 10)
    
    # Cost: 40, Duals: 100(Node1)
    # RC = 40 - 100(第一次) - 100(第二次) = -160
    duals = [0, 100.0, 0] 
    
    # Node 2 的邻居列表不包含 1 -> 导致“忘记”去过 1
    b.ng_sets = [
        [0, 1, 2],
        [0, 1, 2],
        [0, 2] # 关键：2 不记 1
    ]
    
    solver = m.LabelingSolver(b.to_cpp_input(), 0.5)
    paths = solver.solve(duals)
    
    # 应该能找到循环路径
    assert [0, 1, 2, 1, 0] in paths

def test_espprc_no_cycle():
    """测试 ESPPRC 不允许循环 (全集记忆)"""
    b = PricingDataBuilder(3)
    b.set_edge(0, 1, 10)
    b.set_edge(1, 2, 10)
    b.set_edge(2, 1, 10)
    b.set_edge(1, 0, 10)
    duals = [0, 100.0, 0] # 奖励很大，诱惑它走循环

    # 全集记忆，谁也别想忘
    b.ng_sets = [
        [0, 1, 2],
        [0, 1, 2],
        [0, 1, 2] # 关键：2 记得 1，应该禁止回访
    ]

    solver = m.LabelingSolver(b.to_cpp_input(), 0.5)
    paths = solver.solve(duals)

    # 绝对不应该包含循环路径
    for path in paths:
        assert path != [0, 1, 2, 1, 0], f"Found invalid cycle path: {path}"