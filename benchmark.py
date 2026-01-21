import os
import csv
import time
from datetime import datetime
from src.instance import VRPTWInstance
from src.branching import BranchAndBoundEngine # <--- 改用 B&P 引擎

# ==========================================
# 1. 配置区域 (在这里修改测试列表)
# ==========================================
TARGET_INSTANCES = [
    "C101", "C102",
    "R101", "R102",
    # "RC101", "RC102" 
]

# 每个算例的最大运行时间 (秒)
GLOBAL_TIME_LIMIT = 10

# 车辆固定成本 (用于还原纯距离)
VEHICLE_FIXED_COST = 2000.0

# ==========================================
# 2. Solomon 100 节点 BKS
# ==========================================
SOLOMON_BKS = {
    # C1 Series
    "C101": (828.94, 10), "C102": (828.94, 10), "C103": (828.06, 10),
    "C104": (824.78, 10), "C105": (828.94, 10), "C106": (828.94, 10),
    "C107": (828.94, 10), "C108": (828.94, 10), "C109": (828.94, 10),
    # R1 Series
    "R101": (1607.7, 19), "R102": (1468.4, 17), "R103": (1208.7, 13),
    "R104": (971.5, 9),   "R105": (1355.3, 14), "R106": (1234.6, 12),
    "R107": (1064.6, 10), "R108": (932.1, 9),   "R109": (1146.9, 11),
    "R110": (1068.0, 10), "R111": (1048.7, 10), "R112": (953.63, 9),
    # RC1 Series
    "RC101": (1619.8, 14), "RC102": (1457.4, 12), "RC103": (1258.0, 11),
    "RC104": (1132.3, 10), "RC105": (1513.7, 13), "RC106": (1365.6, 11),
    "RC107": (1207.8, 11), "RC108": (1114.2, 10)
}

def run_benchmark(data_dir="data", output_dir="result/benchmark_bnb"):
    # 1. 准备输出
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = os.path.join(output_dir, f"bnb_results_{timestamp}.csv")
    
    # 2. 定义表头
    headers = [
        "Instance", 
        "Time(s)",
        "Status",       # Optimal / Feasible / Infeasible
        "Total_Obj",    # 含固定成本
        "Pure_Dist",    # 纯距离 (Obj - 2000*k)
        "BKS_Dist",     # 已知最优距离
        "Gap_Pct",      # (Pure - BKS)/BKS
        "Trucks", 
        "BKS_Trucks"
    ]
    
    results = []
    
    print(f"🚀 Starting B&P Benchmark on {len(TARGET_INSTANCES)} instances...")
    print(f"⏱️  Time Limit per instance: {GLOBAL_TIME_LIMIT}s")
    print("-" * 80)

    # 3. 循环运行
    for name in TARGET_INSTANCES:
        base_name = os.path.basename(name).split('.')[0]
        file_path = os.path.join(data_dir, f"{base_name}.txt")
        
        if not os.path.exists(file_path):
            print(f"❌ Error: File not found {file_path}")
            continue
            
        print(f"Running {base_name}...", end=" ", flush=True)
        
        try:
            # --- 加载数据 ---
            # verbose=False: 关闭详细的列生成日志，只保留关键信息
            instance = VRPTWInstance(file_path, verbose=False)
            
            # --- 初始化 B&P 引擎 ---
            bnb_engine = BranchAndBoundEngine(instance, verbose=False)
            
            # --- 计时开始 ---
            start_time = time.perf_counter()
            
            # 调用 solve，传入时间限制
            final_obj, final_routes = bnb_engine.solve(global_time_limit=GLOBAL_TIME_LIMIT)
            
            end_time = time.perf_counter()
            run_time = end_time - start_time
            
            # --- 数据处理 ---
            num_trucks = len(final_routes)
            
            if final_routes and final_obj < float('inf'):
                # 成功找到解
                status = "Optimal" # 或者 Feasible (如果是因为超时停止的)
                if run_time > GLOBAL_TIME_LIMIT:
                    status = "TimeLimit"
                
                # 计算纯距离
                pure_dist = final_obj - (num_trucks * VEHICLE_FIXED_COST)
                
                # 获取 BKS
                bks_dist, bks_trucks = SOLOMON_BKS.get(base_name, (0, 0))
                
                # 计算 Gap
                if bks_dist > 0:
                    gap_pct = (pure_dist - bks_dist) / bks_dist * 100
                else:
                    gap_pct = 0.0
                
                # 打印单行结果摘要
                print(f"✅ Done. Dist: {pure_dist:.2f} (Gap: {gap_pct:.2f}%) | Time: {run_time:.2f}s")
            
            else:
                # 无解
                status = "Infeasible"
                pure_dist = float('inf')
                gap_pct = float('inf')
                bks_dist, bks_trucks = SOLOMON_BKS.get(base_name, (0, 0))
                print(f"⚠️ No Solution Found.")

            # --- 记录 ---
            row = {
                "Instance": base_name,
                "Time(s)": round(run_time, 2),
                "Status": status,
                "Total_Obj": round(final_obj, 2) if final_obj < float('inf') else "inf",
                "Pure_Dist": round(pure_dist, 2) if pure_dist < float('inf') else "inf",
                "BKS_Dist": bks_dist,
                "Gap_Pct": f"{gap_pct:.2f}%" if gap_pct < float('inf') else "inf",
                "Trucks": num_trucks,
                "BKS_Trucks": bks_trucks
            }
            results.append(row)
            
        except Exception as e:
            print(f"\n❌ Crashed! Error: {e}")
            import traceback
            traceback.print_exc()

    # 4. 写入 CSV
    if results:
        with open(csv_filename, mode='w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(results)
            
        print("-" * 80)
        print(f"📊 Benchmark Summary saved to: {csv_filename}")
        print("-" * 80)
        
        # 打印漂亮的控制台表格
        print(f"{'Instance':<10} {'Dist':<10} {'BKS':<10} {'Gap':<10} {'Time':<10} {'Veh':<5}")
        print("-" * 60)
        for r in results:
            dist_str = str(r['Pure_Dist'])
            print(f"{r['Instance']:<10} {dist_str:<10} {r['BKS_Dist']:<10} {r['Gap_Pct']:<10} {r['Time(s)']:<10} {r['Trucks']:<5}")
    else:
        print("No results generated.")

if __name__ == "__main__":
    run_benchmark()