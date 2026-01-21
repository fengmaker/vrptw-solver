import gurobipy as gp
from gurobipy import GRB
from typing import List, Tuple, NamedTuple

# 定义一个简单的结构体返回结果
class RouteVal(NamedTuple):
    path: List[int]
    val: float

class MasterProblem:
    def __init__(self, instance, verbose=True) -> None:
        self.verbose = verbose
        self.inst = instance
        self.model = gp.Model("VRPTW_Master")
        self.model.setParam('OutputFlag', 0)
        
        # 车辆固定成本
        self.vehicle_fixed_cost = 2000.0 
        
        # === [修复关键点 1] 初始化两个同步列表 ===
        self.routes = []  # 存储路径结构 List[List[int]]
        self.vars = []    # 存储对应的 Gurobi 变量 List[gp.Var]
        
        self.constrs = {}
        self._init_model()

    def _init_model(self):
        """初始化模型结构"""
        # 覆盖约束
        for i in range(1, self.inst.num_nodes):
            self.constrs[i] = self.model.addConstr(gp.LinExpr() >= 1, name=f"cover_{i}")
        
        # 初始虚拟列 (Big-M)
        self._init_dummy_columns()

    def _init_dummy_columns(self) -> None:
        big_m = 100000.0 
        for i in range(1, self.inst.num_nodes):
            col = gp.Column()
            col.addTerms(1.0, self.constrs[i])
            # 添加变量
            var = self.model.addVar(obj=big_m + self.vehicle_fixed_cost, column=col, name=f"dummy_{i}")
            
            # === [修复关键点 2] 两个列表同步添加 ===
            self.vars.append(var)
            self.routes.append([0, i, 0]) 

    def solve(self) -> Tuple[float, List[float]]:
        """求解 RMP (线性松弛)"""
        # 确保是连续模型
        for v in self.model.getVars():
            if v.vType != GRB.CONTINUOUS:
                v.vType = GRB.CONTINUOUS
                
        self.model.optimize()
        
        if self.model.Status == GRB.INFEASIBLE:
            # 尝试计算 IIS 以帮助调试，虽然这里直接返回 inf
            # self.model.computeIIS() 
            return float('inf'), []
        
        duals = [0.0] * self.inst.num_nodes
        for i in range(1, self.inst.num_nodes):
            duals[i] = self.constrs[i].Pi
            
        return self.model.ObjVal, duals

    def add_route(self, route_label) -> None:
        """添加新列"""
        path = route_label.get_path()
        phys_cost = 0.0
        for k in range(len(path)-1):
            u, v = path[k], path[k+1]
            phys_cost += self.inst.dist_matrix[u][v]
        
        total_cost = phys_cost + self.vehicle_fixed_cost
        
        col = gp.Column()
        for node in path:
            if node != 0:
                col.addTerms(1.0, self.constrs[node])
        
        # 注册变量
        var = self.model.addVar(obj=total_cost, column=col, name=f"route_{len(self.routes)}")
        
        # === [修复关键点 3] 两个列表同步添加 ===
        self.routes.append(path)
        self.vars.append(var)

    def deactivate_columns(self, forbidden_arcs: List[Tuple[int, int]]):
        """
        [关键逻辑] 根据禁止边列表，禁用所有包含这些边的旧列。
        方法：将对应的变量 Upper Bound (UB) 设为 0。
        """
        if not forbidden_arcs:
            return

        # 1. 建立快速查询集
        forbidden_set = set(forbidden_arcs)
        
        # 2. 遍历所有路径
        # 注意：vars 和 routes 的长度必须一致
        for i, route in enumerate(self.routes):
            var = self.vars[i]
            
            # 检查该路径是否包含禁止边
            is_violated = False
            for k in range(len(route)-1):
                edge = (route[k], route[k+1])
                if edge in forbidden_set:
                    is_violated = True
                    break
            
            # 3. 设置界限
            if is_violated:
                var.UB = 0.0  # 禁用
            else:
                # 只有之前被禁用的才需要恢复，这里简单起见全部设为 inf 也可以
                # 或者更严谨一点：只在没有其他约束时恢复
                # 在简单的分支策略中，我们假设父节点的约束子节点都继承，所以不需要恢复操作
                # 但为了代码健壮性，我们可以重置为 inf (如果逻辑是每一轮重新应用所有约束)
                var.UB = float('inf') 

    def get_fractional_solution(self) -> List[RouteVal]:
        """获取当前 LP 的非零解"""
        active_routes = []
        for i, var in enumerate(self.vars):
            try:
                val = var.x
            except AttributeError:
                val = 0.0
            
            if val > 1e-4: # 忽略浮点误差
                active_routes.append(RouteVal(self.routes[i], val))
        return active_routes

    def solve_integer(self) -> Tuple[float, List[List[int]]]:
        """求解整数解 (MIP)"""
        # 1. 转换为二值变量
        for var in self.model.getVars():
            var.vType = GRB.BINARY
        
        self.model.setParam('TimeLimit', 60)
        self.model.setParam('OutputFlag', 1 if self.verbose else 0)
        self.model.optimize()
        
        if self.model.SolCount > 0:
            selected_routes = []
            total_dist = 0.0
            
            for var, route in zip(self.vars, self.routes): # 使用 zip 安全遍历
                if var.x > 0.5:
                    # 计算物理距离
                    d = 0.0
                    for k in range(len(route)-1):
                        d += self.inst.dist_matrix[route[k]][route[k+1]]
                    total_dist += d
                    selected_routes.append(route)
            return total_dist, selected_routes
        else:
            return float('inf'), []