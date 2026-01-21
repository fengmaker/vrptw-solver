from operator import is_
import time
from typing import List, Tuple, NamedTuple, Optional
import math
from collections import defaultdict

# 引入你的求解器组件
# 假设 CGSolver 在 src.solver 中 (根据之前的 import 路径)
from src.solver import CGSolver

class BranchConstraint(NamedTuple):
    """
    分支约束定义
    kind=0: 禁止边 (u->v), 对应 x_uv = 0
    kind=1: 强制边 (u->v), 对应 x_uv = 1
    """
    u: int
    v: int
    kind: int 

class TreeNode:
    def __init__(self, parent=None, constraints=None):
        self.id = 0 # 唯一ID，由 Engine 分配
        self.parent = parent
        # 继承父节点约束 + 新增约束
        self.constraints: List[BranchConstraint] = []
        if parent:
            self.constraints.extend(parent.constraints)
        if constraints:
            self.constraints.extend(constraints)
            
        self.obj_val = float('inf')
        self.is_integer = False
        self.routes = [] # 该节点生成的列/解

class BranchAndBoundEngine:
    def __init__(self, instance, verbose=True):
        self.instance = instance
        self.verbose = verbose
        # 初始化一个 CGSolver 实例作为底层工头
        self.cg_solver = CGSolver(instance, verbose=False) 
        
        self.best_integer_obj = float('inf')
        self.best_routes = []
        self.nodes_explored = 0
        self.start_time = 0

    def solve(self,global_time_limit=60): 
        self.start_time = time.time()
        print(f"=== Starting Branch-and-Price (Time Limit: {global_time_limit}s) ===")
        
        # 1. 创建根节点
        root = TreeNode()
        stack = [root] # 使用栈实现 DFS (深度优先搜索)
        
        while stack:
            if time.time() - self.start_time > global_time_limit:
                print(f"\n⏰ Global Time Limit ({global_time_limit}s) Reached!")
                print("   -> Stopping Search.")
                print("   -> Running Final MIP on collected columns...")
                break # 跳出 while 循环
            node = stack.pop()
            self.nodes_explored += 1
            
            # 2. 处理当前节点
            if self.verbose:
                indent = "-" * len(node.constraints)
                print(f"{indent}Node {self.nodes_explored} | Constrs: {len(node.constraints)}")

            # 3. 运行列生成 (CG)
            # 我们需要让 CGSolver 支持传入约束
            is_feasible, obj, routes = self._solve_node(node)
            
            # 4. 剪枝逻辑 (Pruning)
            # 情况 A: 无解
            if not is_feasible:
                if self.verbose: print(f"{indent} -> Infeasible / Pruned")
                continue
            
            # 情况 B: 目标值比当前最优整数解还差 (Bound)
            if obj >= self.best_integer_obj - 1e-4:
                if self.verbose: print(f"{indent} -> Pruned by Bound ({obj:.2f} >= {self.best_integer_obj:.2f})")
                continue
            
            node.obj_val = obj
            node.routes = routes
            
            # 5. 检查整数性 & 分支
            fractional_edge = self._find_most_fractional_edge(routes)
            
            if fractional_edge is None:
                # 找到整数解！
                print(f"New Integer Solution Found: {obj:.2f}")
                self.best_integer_obj = obj
                self.best_routes = routes
            else:
                # 需要分支
                u, v, val = fractional_edge
                if self.verbose:
                    print(f"{indent} -> Branching on ({u}, {v}) val={val:.2f}")
                
                # 创建两个子节点
                # Child 1: 强制走 (u, v) -> x_uv = 1
                # 策略：通常先搜 "强制" 分支更容易找到可行整数解（Heuristic）
                child_1_constrs = [BranchConstraint(u, v, 1)]
                child_1 = TreeNode(parent=node, constraints=child_1_constrs)
                
                # Child 0: 禁止走 (u, v) -> x_uv = 0
                child_0_constrs = [BranchConstraint(u, v, 0)]
                child_0 = TreeNode(parent=node, constraints=child_0_constrs)
                
                # 入栈顺序决定搜索顺序。后进先出。
                # 如果 val > 0.5 (比如 0.9)，说明这一边很可能在最优解里，我们想先搜 x=1
                # 所以先压入 Child 0，再压入 Child 1
                if val > 0.5:
                    stack.append(child_0)
                    stack.append(child_1)
                else:
                    stack.append(child_1)
                    stack.append(child_0)
        final_mip_dist, final_mip_routes = self.cg_solver.master.solve_integer()
        fixed_cost = 2000.0
        final_mip_obj = final_mip_dist + (len(final_mip_routes) * fixed_cost)

        if final_mip_obj < self.best_integer_obj:
            print(f"Final MIP found best solution: {final_mip_obj:.2f} (Dist: {final_mip_dist:.2f})")
            self.best_integer_obj = final_mip_obj
            self.best_routes = final_mip_routes
        print(f"\n=== B&P Finished in {time.time() - self.start_time:.2f}s ===")
        print(f"Nodes Explored: {self.nodes_explored}")
        print(f"Best Integer Obj: {self.best_integer_obj}")
        return self.best_integer_obj, self.best_routes

    def _solve_node(self, node: TreeNode) -> Tuple[bool, float, List]:
        """
        在特定节点上运行 CG。
        核心任务：将 node.constraints 翻译成 CGSolver 能懂的 forbidden_arcs
        """
        # 1. 翻译约束
        #    C++ 只懂 "Forbidden Arcs"。
        #    Python 需要把 "Mandatory Arcs" 转化为一堆 "Forbidden Arcs"。
        forbidden_arcs = []
        
        # 同时我们也需要在 Master Problem 里禁用包含非法边的列
        # 但为简单起见，我们先依靠 Pricing 生成不出非法列，
        # 并依靠 Master 的约束重新优化来“清洗”掉旧列（如果需要的话，通常需要 Reset Master 或清除旧列）
        
        # 这是一个关键点：最简单的做法是每次 Reset Solver，或者在 Solve 前
        # 告诉 CGSolver 清理不符合当前约束的列。
        # 这里我们采用“传参给 Pricing”策略。
        
        for c in node.constraints:
            if c.kind == 0: # 禁止 u->v
                forbidden_arcs.append((c.u, c.v))
            elif c.kind == 1: # 强制 u->v
                # 强制 u->v 意味着：
                # 1. u 不能去任何非 v 的地方
                for k in range(self.instance.num_nodes):
                    if k != c.v:
                        forbidden_arcs.append((c.u, k))
                # 2. 任何非 u 的点不能去 v
                for k in range(self.instance.num_nodes):
                    if k != c.u:
                        forbidden_arcs.append((k, c.v))
        
        # 2. 调用 CGSolver
        # 我们需要修改 CGSolver.run() 或者单独写一个 run_with_constraints
        # 为了不破坏原有逻辑，建议扩展 CGSolver
        # 1. 跑列生成 (LP), obj 包含固定成本 (20857.25)
        is_feasible, obj, routes = self.cg_solver.solve_with_constraints(forbidden_arcs)
        
        if not is_feasible:
            return False, 0.0, []
        return True, obj, routes

    def _find_most_fractional_edge(self, routes) -> Optional[Tuple[int, int, float]]:
        """
        计算每条边的流量，找到最接近 0.5 的边。
        Edge Flow = sum( lambda_r * I((u,v) in r) )
        """
        edge_flows = defaultdict(float)
        
        # 注意：这里我们假设 routes 包含 (path_list, lambda_value)
        # 如果 CGSolver 只返回 path_list，我们需要去 Master 获取 lambda
        # 这是一个集成点。
        
        for route_obj in routes:
            # route_obj 结构取决于 CGSolver 返回什么
            # 假设是对象: route.path (List[int]), route.val (float)
            path = route_obj.path
            val = route_obj.val # 对偶变量? 不，是主问题变量值 lambda
            
            if val < 1e-4: continue # 忽略未选中的列
            
            for k in range(len(path)-1):
                u, v = path[k], path[k+1]
                edge_flows[(u,v)] += val
        
        best_edge = None
        min_diff = 0.5 # 我们要找离 0.5 最近的，即 |val - 0.5| 最小
        
        for (u, v), flow in edge_flows.items():
            # 忽略 Depot 相关的边 (0->x, x->0)，通常不对它们分支，或者优先级低
            # 也可以分支，看策略。这里先分支内部边。
            # if u == 0 or v == 0: continue 
            
            diff = abs(flow - 0.5)
            if diff < 0.5 - 1e-4: # 即 flow 在 (0, 1) 之间
                if diff < min_diff:
                    min_diff = diff
                    best_edge = (u, v, flow)
        
        return best_edge