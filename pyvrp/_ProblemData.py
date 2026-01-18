import numpy as np
from typing import List, Optional

class Client:
    """客户点：存储坐标、需求、时间窗等原始数据"""
    def __init__(
        self, 
        x: float, 
        y: float, 
        delivery: List[int] = None, 
        service_duration: int = 0, 
        tw_early: int = 0, 
        tw_late: int = 2147483647, # 默认 MAX_INT
        name: str = ""
    ):
        self.x = x
        self.y = y
        self.delivery = delivery if delivery else [0]
        self.service_duration = service_duration
        self.tw_early = tw_early
        self.tw_late = tw_late
        self.name = name

class Depot:
    """仓库点：车辆的起点和终点"""
    def __init__(self, x: float, y: float, tw_early: int = 0, tw_late: int = 2147483647, name: str = ""):
        self.x = x
        self.y = y
        self.tw_early = tw_early
        self.tw_late = tw_late
        self.name = name

class ProblemData:
    """
    核心数据类：
    将所有的 Client 和 Depot 数据“冻结”为 NumPy 矩阵，供算法快速查表。
    """
    def __init__(
        self,
        clients: List[Client],
        depots: List[Depot],
        vehicle_capacity: int,
        dist_matrix: np.ndarray,
        duration_matrix: np.ndarray = None
    ):
        self._clients = clients
        self._depots = depots
        self._vehicle_capacity = vehicle_capacity
        
        # 核心矩阵：用于高性能计算
        self._dist_matrix = dist_matrix
        self._duration_matrix = duration_matrix if duration_matrix is not None else dist_matrix
        
        # 预提数组：避免在循环中访问对象属性，直接访问 NumPy 数组快得多
        self._demands = np.array([0] + [c.delivery[0] for c in clients]) # 0号是Depot
        self._tws = np.array([[d.tw_early, d.tw_late] for d in depots] + 
                             [[c.tw_early, c.tw_late] for c in clients])
        self._service_durations = np.array([0] + [c.service_duration for c in clients])

    @property
    def num_clients(self) -> int:
        return len(self._clients)

    @property
    def num_locations(self) -> int:
        return len(self._clients) + len(self._depots)

    def dist(self, i: int, j: int) -> int:
        return self._dist_matrix[i, j]

    def demand(self, i: int) -> int:
        return self._demands[i]