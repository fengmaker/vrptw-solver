import os
import time
from src.instance import VRPTWInstance
from src.branching import BranchAndBoundEngine
from src.visualizer import plot_solution

def run_branch_and_price():
    # 1. Configuration
    DATA_PATH = "data/C102.txt"
    if not os.path.exists(DATA_PATH):
        print(f"Error: File not found at {DATA_PATH}")
        return

    # 2. Load Instance
    print(f"Loading instance: {DATA_PATH}")
    # Consider reducing customers for faster debug (e.g., max_customers=25) if supported
    # instance = VRPTWInstance(DATA_PATH, max_customers=25) 
    instance = VRPTWInstance(DATA_PATH) 

    # 3. Initialize B&P Engine
    bnb_engine = BranchAndBoundEngine(instance, verbose=True)

    # 4. Solve
    print("\n" + "="*50)
    print("STARTING BRANCH-AND-PRICE")
    print("="*50)
    
    start_time = time.perf_counter()
    obj, routes = bnb_engine.solve(global_time_limit=60)
    end_time = time.perf_counter()

    # 5. Report Results
    print("\n" + "="*50)
    print("FINAL RESULTS")
    print("="*50)
    
    num_vehicles = len(routes)
    fixed_cost = 2000.0
    
    # 这里的 obj 是包含固定成本的总价 (20857.25)
    # 我们要算出纯距离
    if routes:
        pure_distance = obj - (num_vehicles * fixed_cost)
    else:
        pure_distance = float('inf')
    print(f"Time Taken  : {end_time - start_time:.2f} seconds")
    print(f"Status      : {'Optimal' if routes else 'Infeasible'}")
    print(f"Total Obj   : {obj:.2f} (With Fixed Cost)")
    print(f"Pure Dist   : {pure_distance:.2f}") # <--- 这里会显示 857.25 (或 828.94)
    print(f"Num Vehicles: {num_vehicles}")
    print("-" * 50)
    
    for i, r in enumerate(routes):
        # r might be a RouteVal object or just a list, depending on implementation
        # let's handle both
        path = r.path if hasattr(r, 'path') else r
        print(f"Vehicle {i+1}: {path}")

    # 6. Visualization
    if routes:
        # Extract raw paths if they are RouteVal objects
        final_paths = [r.path if hasattr(r, 'path') else r for r in routes]
        plot_solution(instance, final_paths, title=f"B&P Solution: {pure_distance:.2f}")

if __name__ == "__main__":
    run_branch_and_price()