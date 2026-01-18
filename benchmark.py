import os
import time
import json
import pandas as pd
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

# 导入你的求解器 (假设路径没变)
from src.instance import VRPTWInstance
from src.solver import CGSolver

# ==========================================
# 0. Solomon C1 系列 BKS (Best Known Solution)
# 格式: "Instance": (Distance, Vehicles)
# 数据来源: SINTEF / Solomon Benchmark Website (100 customers)
# ==========================================
def load_bks(json_path):
    try:
        with open(json_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: BKS file not found at {json_path}. Gaps will be 0.")
        return {}

# ==========================================
# 1. 你的 CG Solver 包装器
# ==========================================
def run_my_cg_solver(filepath, time_limit):
    try:
        instance = VRPTWInstance(filepath, verbose=False)
        solver = CGSolver(instance, verbose=False)
        
        # 限制 Master 时间 (Soft limit for CG)
        if hasattr(solver.master, 'model'):
            solver.master.model.setParam('TimeLimit', time_limit)
        
        start = time.time()
        # 假设 solver.run() 返回 (best_distance, routes_list)
        dist, routes = solver.run()
        end = time.time()
        
        return dist, end - start, len(routes)
    except Exception as e:
        print(f"  [MyCG Error]: {e}")
        return float('inf'), 0.0, 0

# ==========================================
# 2. OR-Tools 求解器
# ==========================================
def run_ortools(filepath, time_limit):
    """
    运行 OR-Tools 并返回 (Obj, Time, NumVehicles)
    """
    instance = VRPTWInstance(filepath)
    scale = 100 # 精度缩放
    
    # 构建数据模型
    data = {}
    data['time_matrix'] = [[int(instance.dist_matrix[i][j] * scale) for j in range(instance.num_nodes)] for i in range(instance.num_nodes)]
    data['time_windows'] = [(int(c.tw_a * scale), int(c.tw_b * scale)) for c in instance.customers]
    data['demands'] = [int(c.demand) for c in instance.customers]
    data['vehicle_capacities'] = [int(instance.vehicle_capacity)] * instance.vehicle_count
    data['num_vehicles'] = instance.vehicle_count
    data['depot'] = 0

    manager = pywrapcp.RoutingIndexManager(len(data['time_matrix']), data['num_vehicles'], data['depot'])
    routing = pywrapcp.RoutingModel(manager)

    # 1. Distance/Time Cost
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        # OR-Tools Cost 通常包含 Service Time，但物理距离计算需注意
        service = int(instance.customers[from_node].service_time * scale)
        return data['time_matrix'][from_node][to_node] + service

    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # 2. Capacity Constraint
    def demand_callback(from_index):
        return data['demands'][manager.IndexToNode(from_index)]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index, 0, data['vehicle_capacities'], True, 'Capacity')

    # 3. Time Window Constraint
    routing.AddDimension(
        transit_callback_index, 
        int(100000 * scale), int(100000 * scale), 
        False, 'Time')
    time_dimension = routing.GetDimensionOrDie('Time')
    for location_idx, (start, end) in enumerate(data['time_windows']):
        if location_idx == 0: continue
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(start, end)

    # Search Parameters
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
    search_parameters.local_search_metaheuristic = (routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
    search_parameters.time_limit.seconds = time_limit
    # search_parameters.log_search = True # 如果想看 OR-Tools 的实时日志可以打开

    start_time = time.time()
    solution = routing.SolveWithParameters(search_parameters)
    end_time = time.time()

    if solution:
        total_dist = 0
        vehicle_count = 0
        for vehicle_id in range(data['num_vehicles']):
            index = routing.Start(vehicle_id)
            route_dist = 0
            has_customer = False
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                if node_index != 0: has_customer = True
                previous_index = index
                index = solution.Value(routing.NextVar(index))
                # 重新计算真实的物理距离（不含服务时间）
                u = manager.IndexToNode(previous_index)
                v = manager.IndexToNode(index)
                route_dist += instance.dist_matrix[u][v]
            
            if has_customer:
                total_dist += route_dist
                vehicle_count += 1
        return total_dist, end_time - start_time, vehicle_count
    else:
        return float('inf'), time_limit, 0

# ==========================================
# 3. 主程序
# ==========================================

if __name__ == "__main__":
    data_dir = "data/"
    bks_path = "data/solomon_bks.json" # 指向你新建的 json 文件
    
    # 1. 加载 BKS
    bks_data = load_bks(bks_path)
    
    results = []
    
    # 2. 扫描所有 C 开头的文件 (C1xx, C2xx)
    files = [f for f in os.listdir(data_dir) if f.startswith("C") and f.endswith(".txt")]
    files.sort()
    
    header = (
        f"{'Inst':<8} | {'Method':<10} | {'Obj':<10} | {'Truck':<5} | "
        f"{'CPU(s)':<8} | {'Gap(%)':<8} | {'TrkDiff':<7} | {'BKS(Obj/Trk)':<15}"
    )
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for filename in files[:1]:
        instance_name = filename.split(".")[0]
        
        # 只跑 BKS 文件里有的，防止跑偏
        if instance_name not in bks_data:
            continue
            
        path = os.path.join(data_dir, filename)
        
        # 获取该算例的 BKS
        bks_obj = bks_data[instance_name]['distance']
        bks_veh = bks_data[instance_name]['vehicles']
        
        limit = 10 # 60秒限制

        def process_result(method_name, obj, time_used, veh):
            # 防止除以0
            if bks_obj > 0:
                gap_pct = ((obj - bks_obj) / bks_obj) * 100
            else:
                gap_pct = 0.0
            
            trk_diff = veh - bks_veh
            
            print(
                f"{instance_name:<8} | {method_name:<10} | {obj:<10.2f} | {veh:<5} | "
                f"{time_used:<8.2f} | {gap_pct:<8.2f} | {trk_diff:<7} | {bks_obj:.1f}/{bks_veh}"
            )
            
            results.append({
                'Instance': instance_name,
                'Method': method_name,
                'Obj': obj,
                'Trucks': veh,
                'Time': time_used,
                'Gap_Pct': gap_pct,
                'Truck_Diff': trk_diff,
                'BKS_Obj': bks_obj,
                'BKS_Trucks': bks_veh
            })

        # --- Run MyCG ---
        cg_obj, cg_time, cg_veh = run_my_cg_solver(path, limit)
        process_result("MyCG", cg_obj, cg_time, cg_veh)

        # --- Run OR-Tools ---
        or_obj, or_time, or_veh = run_ortools(path, limit)
        process_result("OR-Tools", or_obj, or_time, or_veh)

        print("-" * len(header))

    # 保存 CSV
    df = pd.DataFrame(results)
    df.to_csv("benchmark_all_c.csv", index=False)
    print("\nBenchmark saved to benchmark_all_c.csv")