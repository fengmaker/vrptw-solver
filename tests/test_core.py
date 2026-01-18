# tests/test_core.py
import numpy as np
from pyvrp._ProblemData import Client, Depot, ProblemData
import sys

def test_problem_data_initialization():
    print("正在验证 ProblemData 初始化...")
    
    # 1. 定义仓库 (坐标 0,0)
    depot = Depot(x=0.0, y=0.0, tw_early=0, tw_late=1000)
    
    # 2. 定义两个客户
    clients = [
        Client(x=0.0, y=4.0, delivery=[10], service_duration=1, tw_early=0, tw_late=500), # 1号客户
        Client(x=3.0, y=0.0, delivery=[20], service_duration=1, tw_early=0, tw_late=500), # 2号客户
    ]
    
    # 3. 手动构造距离矩阵 (3x3: 0号是Depot, 1, 2是客户)
    # 距离计算：(0,0)->(0,4)=4; (0,0)->(3,0)=3; (0,4)->(3,0)=5
    dist_mat = np.array([
        [0, 4, 3],
        [4, 0, 5],
        [3, 5, 0]
    ])
    
    # 4. 创建 ProblemData
    data = ProblemData(
        clients=clients,
        depots=[depot],
        vehicle_capacity=50,
        dist_matrix=dist_mat
    )
    
    # 5. 断言验证 (Assert)
    assert data.num_clients == 2
    assert data.num_locations == 3
    assert data.demand(1) == 10
    assert data.dist(1, 2) == 5
    
    print("✅ ProblemData 静态验证通过！")

if __name__ == "__main__":
    print(f"Python 现在的搜索起点是: {sys.path[0]}")
    test_problem_data_initialization()