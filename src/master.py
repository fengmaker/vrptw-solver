import gurobipy as gp
from gurobipy import GRB
from typing import List, Tuple

class MasterProblem:
    def __init__(self, instance,verbose=True) -> None:
        self.verbose = verbose # <--- 保存开关
        self.inst = instance
        self.model = gp.Model("VRPTW_Master")
        self.model.setParam('OutputFlag', 0) # 默认关闭输出
        self.vehicle_fixed_cost = 2000.0  # 建议先设 2000，设 10000 可能导致数值不稳定
        self.routes = [] 
        self.constrs = {}
        
        # 初始化覆盖约束
        # 客户编号从 1 到 N-1 (0 是 Depot)
        for i in range(1, self.inst.num_nodes):
            self.constrs[i] = self.model.addConstr(gp.LinExpr() >= 1, name=f"cover_{i}") # 每个客户至少被覆盖一次 每一个客户都有一个约束，也有相应的对偶变量
        self._init_dummy_columns()

    def _init_dummy_columns(self) -> None:
        """
        初始化虚拟列以确保初始可行性
        1. 每个客户 i 都有一个虚拟列，表示单独一辆车从仓库出发服务该客户后返回仓库。
        2. 这些虚拟列的成本设置为一个很大的数 (Big-M) 加上车辆固定成本，确保在没有更优路径时才会被选中。
        3. 这样做的目的是保证主问题一开始就是可行的。
        """
        # --- 2. 这里的 Big-M 必须比 fixed_cost 大得多 ---
        big_m = 100000.0 
        for i in range(1, self.inst.num_nodes):
            col = gp.Column()
            col.addTerms(1.0, self.constrs[i]) # 对应数学公式里的那一列 a_{ir} (表明这条路径服务了谁)
            # 虚拟列也要加上 fixed_cost (逻辑上)
            self.model.addVar(obj = big_m + self.vehicle_fixed_cost, column=col, name=f"lambda_{i}")
            # # 对应数学公式里的 c_r  #    # 给变量 λ_r 起个名字
            self.routes.append([0, i, 0])     

    def solve(self) -> Tuple[float, List[float]]:
        """
        求解线性松弛主问题 (RMP)。
        
        Returns:
            Tuple[float, List[float]]: 
                - float: 当前主问题的目标函数值 (Objective Value)
                - List[float]: 对偶值列表 (Dual Values)，下标对应客户ID
        """
        self.model.optimize()
        
        if self.model.Status == GRB.INFEASIBLE:  # 1. 处理无解情况
            print("Master Problem Infeasible!")
            self.model.computeIIS()
            return float('inf'), []  # 返回无穷大成本，和空的对偶值列表
        
        duals: List[float] = [0.0] * self.inst.num_nodes  # 2. 获取对偶值
        
        for i in range(1, self.inst.num_nodes):  # 遍历所有客户约束提取 Pi
            duals[i] = self.constrs[i].Pi  
            
        return self.model.ObjVal, duals  # 3. 返回 (Obj, Duals)
    
    def add_route(self, route_label) -> None:
        """
        [核心功能] 将 Pricing 找到的一条新路径添加到主问题的数学模型中。
        1. 还原路径：从 Label 对象中提取出具体的节点序列。
        2. 核算成本：重新计算这条路径的精确物理距离，并加上车辆启动费。
        3. 注册变量：在 Gurobi 模型中添加一个新的列 (Column/Variable)。

        Args:
            route_label (Label): Pricing 算法返回的标签对象，代表一条从 Depot 到 Depot 的完整路径。
        """
        path = route_label.get_path()
        phys_cost = 0.0
        for k in range(len(path)-1):
            u, v = path[k], path[k+1]
            phys_cost += self.inst.dist_matrix[u][v]

        total_cost = phys_cost + self.vehicle_fixed_cost # --- 目标系数加上固定成本 ---
            
        col = gp.Column()
        for node in path:
            if node != 0:
                col.addTerms(1.0, self.constrs[node])
        
        self.model.addVar(obj=total_cost, column=col, name=f"route_{len(self.routes)}")
        self.routes.append(path)

    def solve_integer(self) -> Tuple[float, List[List[int]]]:
        """
        求解整数解，并分离固定成本与运输成本
        """
        # 1. 转换为整数变量
        for var in self.model.getVars():
            var.vType = GRB.BINARY
        
        # 2. 设置参数
        self.model.setParam('TimeLimit', 60)
        self.model.setParam('OutputFlag', 1 if self.verbose else 0) # 根据开关设置输出
        if self.verbose:
            print("\n=== Solving Integer Master Problem ===")
        self.model.optimize()
        
        if self.model.SolCount > 0:
            
            # 打印一下当前状态
            if self.verbose:
                if self.model.Status == GRB.OPTIMAL:
                    print(">>> Status: OPTIMAL (Perfect solution found)")
                elif self.model.Status == GRB.TIME_LIMIT:
                    print(f">>> Status: TIME_LIMIT (Gap: {self.model.MIPGap:.2%})")
            
                # --- 调用打印函数 ---
                self._print_solution()
            # --- 核心修改：分离成本并提取路径 ---
            selected_routes = []
            total_dist = 0.0
            vehicle_count = 0
            
            for var, route in zip(self.model.getVars(), self.routes):
                actual_path = route
                
                if var.x > 0.5 and var.VarName.startswith("route_"):
                    vehicle_count += 1
                    
                    # 重新计算该路径的纯物理距离 (Double Precision)
                    d = 0.0
                    for k in range(len(actual_path)-1):
                        u, v = actual_path[k], actual_path[k+1]
                        d += self.inst.dist_matrix[u][v]
                    
                    total_dist += d
                    selected_routes.append(actual_path)
            
            return total_dist, selected_routes
        else:
            print("No integer solution found within time limit.")
            return float('inf'), []

    def _print_solution(self):
        """以表格形式打印选中的路径详情"""
        print("\n" + "="*90)
        print(f"{'Vehicle':<10} {'Route':<50} {'Dist':>10} {'Load':>10}")
        print("-" * 90)
        
        count = 1
        for var, route in zip(self.model.getVars(), self.routes):
            # 筛选：被选中(1) 且 不是虚拟列(route_)
            if var.x > 0.5 and var.VarName.startswith("route_"):
                
                # 1. 计算距离
                dist = 0.0
                for k in range(len(route)-1):
                    dist += self.inst.dist_matrix[route[k]][route[k+1]]
                
                # 2. 计算载重
                load = 0.0
                for node in route:
                    if node != 0:
                        load += self.inst.customers[node].demand
                
                # 3. 格式化路径字符串 (太长就截断，保持表格美观)
                route_str = str(route)
                if len(route_str) > 55:
                    route_str = route_str[:52] + "..."
                
                # 4. 表格化打印
                # #<Num>: 左对齐占9格
                # route: 左对齐  占50格
                # dist: 右对齐占10格，保留2位小数
                # load: 右对齐占10格，保留1位小数
                print(f"#{count:<9} {route_str:<50} {dist:>10.2f} {load:>10.1f}")
                count += 1