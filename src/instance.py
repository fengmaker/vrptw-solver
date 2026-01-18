import math
import sys
from tabnanny import verbose
from typing import List
from dataclasses import dataclass

@dataclass(frozen=True) # frozen 使得实例不可变 # 隐含结果：因为它是只读的，所以它可以作为字典的 Key 或放入 Set 集合（这对于写算法至关重要）。
class Customer: 
    id: int
    x: float
    y: float
    demand: int
    tw_a: int  # 最早到达
    tw_b: int  # 最晚到达
    service_time: int  
    
class VRPTWInstance:
    """
    核心数据类：负责读取文件并存储所有全局只读数据。
    """
    def __init__(self, filepath, max_customers=None,verbose=True):
        self.verbose = verbose
        self.customers: List[Customer] = []
        self.vehicle_capacity = 0
        self.vehicle_count = 50
        self.dist_matrix = []
        self.num_nodes = 0
        self.ng_masks = []
        # 1. 读取数据
        self._read_solomon(filepath, max_customers)
        
        # 2. 计算距离矩阵
        self._compute_distance_matrix()
        # 3. 更新节点计数 (State Update)
        self.num_nodes = len(self.customers)
        # 4. 预计算 ng-sets 掩码 Optimization Prep   # 单下划线方法 建议只在类内部或子类中使用。 # 双下滑线就是私有方法，防止子类重写或者外部访问
        self._compute_ng_sets(ng_size=8)
        if self.verbose:
            print(f"Instance loaded: {self.num_nodes} nodes (incl. Depot), Cap={self.vehicle_capacity}")

    def _read_solomon(self, filepath, max_customers):
        """
        读取 Solomon 格式的文本文件。
        """
        print(f"Reading file: {filepath} ...")
        with open(filepath, 'r') as f:
            lines = f.readlines()
            
        section = None
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            if line.startswith("VEHICLE"):
                section = "VEHICLE"
                continue
            elif line.startswith("CUSTOMER"):
                section = "CUSTOMER"
                continue

            if section == "VEHICLE" and not line.startswith("NUMBER"):
                parts = line.split()
                if len(parts) >= 2:
                    self.vehicle_capacity = int(parts[1])
            
            elif section == "CUSTOMER" and not line.startswith("CUST") and line[0].isdigit():
                parts = line.split()
                # Solomon: ID, X, Y, Demand, Ready, Due, Service
                cust = Customer(
                    id=int(parts[0]),
                    x=float(parts[1]),
                    y=float(parts[2]),
                    demand=int(parts[3]),
                    tw_a=int(parts[4]),
                    tw_b=int(parts[5]),
                    service_time=int(parts[6])
                )
                # 限制规模逻辑
                if max_customers is not None and len(self.customers) > max_customers:
                    break
                self.customers.append(cust)
                  
    def _compute_distance_matrix(self):
        """
        计算欧几里得距离矩阵。
        """
        N = len(self.customers)
        self.dist_matrix = [[0.0] * N for _ in range(N)]
        for i in range(N):
            for j in range(N):
                c1 = self.customers[i]
                c2 = self.customers[j]
                d = math.sqrt((c1.x - c2.x)**2 + (c1.y - c2.y)**2)
                # self.dist_matrix[i][j] = round(d, 1)
                self.dist_matrix[i][j] = d # 保留精度，避免四舍五入误差影响算法
                
    def _compute_ng_sets(self, ng_size=8):
        """
        预计算每个节点的 ng-set 掩码。
        ng-set 包含节点本身及其最近的 (ng_size-1) 个邻居。
        """
        self.ng_masks = [0] * self.num_nodes
        
        # 对于每个节点 i
        for i in range(self.num_nodes):
            # 拿到 i 到所有点 j 的距离: (distance, j_index)
            # 注意：如果是 Depot (0)，通常也需要计算，或者根据策略略过
            dists = []
            for j in range(self.num_nodes):
                dists.append((self.dist_matrix[i][j], j))
            
            # 按距离排序 (从小到大)
            dists.sort(key=lambda x: x[0])
            
            # 取前 ng_size 个最近的点 (包含自己，因为自己到自己距离为0)
            # 如果 ng_size 大于节点总数，就取全部
            top_neighbors = dists[:min(ng_size, self.num_nodes)]
            
            # 生成位掩码
            mask = 0
            for _, node_idx in top_neighbors:
                mask |= (1 << node_idx)
            
            self.ng_masks[i] = mask