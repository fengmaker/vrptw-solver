from .master import MasterProblem,RouteVal
from .pricing import PricingSolver
import time
from typing import List, Tuple

class CGSolver:
    def __init__(self, instance,verbose=True):
        self.inst = instance
        self.verbose = verbose
        self.master = MasterProblem(instance,verbose=verbose)
        self.pricing = PricingSolver(instance)
        
    def run(self):
        if self.verbose:
            print("=== Starting Column Generation ===")
        iteration = 0
        while True:
            iteration += 1
            # 1. 解主问题
            obj, duals = self.master.solve()
            if self.verbose:
                print(f"Iter {iteration}: Objective = {obj:.2f}")
            # 2. 解子问题 (Pricing)
            new_routes = self.pricing.solve(duals)
            
            # 3. 收敛检查
            if not new_routes:
                if self.verbose:
                    print("Converged! No negative reduced cost routes found.")
                break
            if self.verbose:
                print(f"  -> Found {len(new_routes)} routes. Best RC: {new_routes[0].cost:.2f}")

            # 4. 添加列
            added_count = 0
            for route in new_routes:
                # 简单的过滤策略
                if route.cost < -0.001:
                    self.master.add_route(route)
                    added_count += 1
            
            if added_count == 0:
                break
        if self.verbose:
            print("\n" + "="*40)
            print("Starting Integer Phase...")
            print("="*40)
        
        final_obj, final_routes = self.master.solve_integer()        
        return final_obj, final_routes
    
    def solve_with_constraints(self, forbidden_arcs: List[Tuple[int, int]]) -> Tuple[bool, float, List[RouteVal]]:
        """
        带约束的列生成主循环
        Returns: (is_feasible, obj_val, routes_with_lambda)
        """
        # print(f"DEBUG: Solving with {len(forbidden_arcs)} forbidden arcs") #
        self.master.deactivate_columns(forbidden_arcs)
        # 定义阶段
        # 最后一级必须是 Exact (bucket_step 极小, limit 极大)
        stages = [
            (2.0, 50,  "Stage 1: Heuristic"), # 加速用
            (0.1, 500, "Stage 2: Exact")      # 兜底用 (模拟 SOTA 的 Exact Labeling)
        ]
        
        # 强制参数
        MAX_ITER = 100
        TIME_LIMIT = 15.0 # 给足时间让 Exact 阶段纠正 Duals
        start_time = time.time()
        
        current_stage = 0 
        iteration = 0
        
        while True:
            iteration += 1
            
            # --- [SOTA 逻辑：收敛检查] ---
            # 只有当处于 Exact 阶段 (Stage 2) 且找不到列时，才允许退出！
            # 否则，即使超时，最好也尝试一次 Exact
            
            # 1. 解主问题
            obj, duals = self.master.solve()
            if obj == float('inf'): return False, float('inf'), []

            # 2. 设定参数
            step, limit, name = stages[current_stage]
            self.pricing.set_params(bucket_step=step, limit=limit)
            
            # 3. 求解子问题
            new_labels = self.pricing.solve(duals, forbidden_arcs)
            neg_rc = [l for l in new_labels if l.cost < -1e-4]
            
            if neg_rc:
                # [情况 A] 找到了负 RC 列
                for label in neg_rc: self.master.add_route(label)
                
                # SOTA 技巧：如果 Exact 阶段找到了列，说明 heuristic 漏了。
                # 但为了利用 heuristic 的速度，我们可以降级回去再跑几轮快车
                # (所谓的 Zig-Zagging)。但在你还没调通前，建议不回退，一直保持 Exact。
                # if current_stage > 0: current_stage = 0 
                
            else:
                # [情况 B] 当前阶段找不到列了
                if current_stage < len(stages) - 1:
                    # 还没到 Exact 阶段？升级！
                    current_stage += 1
                    if self.verbose: print(f"   -> Switching to {stages[current_stage][2]} (Safety Net)...")
                    continue # 立即用新精度再跑一次，不要解主问题
                else:
                    # 已经是 Exact 阶段，且找不到列了
                    # 这才是真正的收敛
                    if self.verbose: print("   ✅ Exact convergence verified.")
                    break
            
            # --- [安全限制] ---
            # 只有在非 Exact 阶段，或者已经跑了很多轮 Exact 后才允许超时退出
            if time.time() - start_time > TIME_LIMIT:
                if current_stage == len(stages) - 1: # 如果在 Exact 阶段超时，那没办法
                    if self.verbose: print("   ⚠️ Time Limit in Exact Stage.")
                    break
                else:
                    # 如果在 Heuristic 阶段超时，强制进入 Exact 跑一次再走
                    if self.verbose: print("   ⚠️ Time Limit -> Forcing Exact Pass.")
                    current_stage = len(stages) - 1
                    continue

        final_obj, _ = self.master.solve()
        fractional_routes = self.master.get_fractional_solution()
        return True, final_obj, fractional_routes
    