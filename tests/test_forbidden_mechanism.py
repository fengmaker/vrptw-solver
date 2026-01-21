import sys
import os

# 1. 确保能找到编译好的 .pyd 文件
# 如果你的 .pyd 在 build/ 下，需要把 build 加入 path
# 根据你的 CMake 设置，它可能在 build/ 或者 build/Release/ 下
sys.path.append(os.path.abspath("build")) 

import pricing_lib # 这就是我们用 pybind11 编译出来的模块

def create_mock_data():
    """创建一个最小化的 3 节点问题 (0 -> 1 -> 2 -> 0)"""
    data = pricing_lib.ProblemData()
    data.num_nodes = 3
    data.vehicle_capacity = 100
    
    # 需求
    data.demands = [0, 10, 10]
    
    # 时间窗 (很宽，不限制)
    data.tw_start = [0.0, 0.0, 0.0]
    data.tw_end = [100.0, 100.0, 100.0]
    data.service_times = [0.0, 10.0, 10.0]
    
    # 距离矩阵 (0->1->0 是最短路)
    # 0 到 1 很近 (cost=10), 0 到 2 很远 (cost=100)
    huge = 1000.0
    data.dist_matrix = [
        [0.0,  10.0, 100.0], # 0 -> ?
        [10.0, 0.0,  10.0],  # 1 -> ?
        [100.0, 10.0, 0.0]   # 2 -> ?
    ]
    
    # 时间矩阵 (简单起见等于距离)
    data.time_matrix = data.dist_matrix
    
    # 邻居列表 (全连接)
    data.neighbors = [
        [1, 2], # 0 的邻居
        [0, 2], # 1 的邻居
        [0, 1]  # 2 的邻居
    ]
    
    # ng-relaxation 邻居 (全集)
    data.ng_neighbor_lists = [[0,1,2], [0,1,2], [0,1,2]]
    
    return data

def test_forbidden():
    print("=== Testing Forbidden Arc Mechanism ===")
    data = create_mock_data()
    
    # bucket_step = 1.0
    solver = pricing_lib.LabelingSolver(data, 1.0)
    
    # 1. Baseline: 不禁止任何边
    # Duals 全为 0，单纯找最短物理路径
    duals = [0.0, 50.0, 0.0]
    
    print("\n[Step 1] Baseline Run (No constraints)")
    routes = solver.solve(duals, []) # 传空列表
    
    if not routes:
        print("Error: No routes found in baseline!")
        return
        
    best_route = routes[0] # 假设第一个是最好的
    print(f"Best Route: {best_route}")
    
    # 预期：在这个图中，0->1->0 (cost 20) 应该优于 0->2->0 (cost 200)
    # 注意：Labeling 算法返回的路径包含 Depot，例如 [0, 1, 0]
    
    # 2. Test: 禁止边 (0, 1)
    forbidden = [(0, 1)]
    print(f"\n[Step 2] Constrained Run (Forbid {forbidden})")
    
    routes_constrained = solver.solve(duals, forbidden)
    
    if not routes_constrained:
        print("Warning: No routes found with constraint (could be disconnected).")
    else:
        new_best = routes_constrained[0]
        print(f"New Best Route: {new_best}")
        
        # 验证逻辑
        # 检查新路径里是否还包含 0->1
        is_violated = False
        for i in range(len(new_best)-1):
            u, v = new_best[i], new_best[i+1]
            if u == 0 and v == 1:
                is_violated = True
                break
        
        if is_violated:
            print("❌ FAILURE: C++ solver ignored the forbidden arc!")
        else:
            print("✅ SUCCESS: Route adhered to constraints.")
            # 如果之前的最佳是 [0, 1, 0]，现在应该变成 [0, 2, 0] 或者 [0, 2, 1, 0] 等
            
if __name__ == "__main__":
    try:
        test_forbidden()
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        print("Did you forget to build the C++ module?")