import vrplib
import numpy as np
from typing import List
from ._ProblemData import Client, Depot, ProblemData

def read(path: str) -> ProblemData:
    """
    读取 Solomon 格式文件并返回 ProblemData 实例
    """
    # 1. 使用 vrplib 解析文件
    instance = vrplib.read_instance(path, instance_format="solomon")
    
    
    # 提取基础数据
    coords = instance['node_coord']
    demands = instance['demand']
    time_windows = instance['time_window']
    service_times = instance['service_time']
    capacity = instance['capacity']
    
    # 2. 识别仓库和客户
    # Solomon 格式中，第一行（索引0）通常是仓库
    depot_coord = coords[0]
    depot_tw = time_windows[0]
    depot = Depot(
        x=float(depot_coord[0]), 
        y=float(depot_coord[1]), 
        tw_early=int(depot_tw[0]), 
        tw_late=int(depot_tw[1]),
        name="Depot"
    )
    
    clients: List[Client] = []
    for i in range(1, len(coords)):
        clients.append(Client(
            x=float(coords[i][0]),
            y=float(coords[i][1]),
            delivery=[int(demands[i])],
            service_duration=int(service_times[i]),
            tw_early=int(time_windows[i][0]),
            tw_late=int(time_windows[i][1]),
            name=f"Client {i}"
        ))
    
    # 3. 计算距离矩阵 (欧氏距离)
    # 使用 NumPy 的广播机制快速计算
    diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
    dist_matrix = np.sqrt(np.sum(diff**2, axis=-1))
    
    # 建议转为整数，这符合 PyVRP 处理高精度距离的习惯（通常乘以一个放大系数再取整）
    # 这里我们先保持原样或四舍五入
    dist_matrix = np.round(dist_matrix).astype(int)

    # 4. 组装并返回
    return ProblemData(
        clients=clients,
        depots=[depot],
        vehicle_capacity=int(capacity),
        dist_matrix=dist_matrix
    )