from .master import MasterProblem
from .pricing import PricingSolver
import time
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
    
    