import os
import csv
import time
import argparse
from datetime import datetime
from src.instance import VRPTWInstance
from src.solver import CGSolver

# ==========================================
# 1. Solomon 100 节点 Best Known Solutions (BKS)
#    格式: "InstanceName": (Distance, Vehicles)
# ==========================================
SOLOMON_BKS = {
    # C1 Series (Clustered)
    "C101": (828.94, 10), "C102": (828.94, 10), "C103": (828.06, 10),
    "C104": (824.78, 10), "C105": (828.94, 10), "C106": (828.94, 10),
    "C107": (828.94, 10), "C108": (828.94, 10), "C109": (828.94, 10),
    # R1 Series (Random)
    "R101": (1607.7, 19), "R102": (1468.4, 17), "R103": (1208.7, 13),
    "R104": (971.5, 9),   "R105": (1355.3, 14), "R106": (1234.6, 12),
    "R107": (1064.6, 10), "R108": (932.1, 9),   "R109": (1146.9, 11),
    "R110": (1068.0, 10), "R111": (1048.7, 10), "R112": (953.63, 9),
    # RC1 Series (Mixed)
    "RC101": (1619.8, 14), "RC102": (1457.4, 12), "RC103": (1258.0, 11),
    "RC104": (1132.3, 10), "RC105": (1513.7, 13), "RC106": (1365.6, 11),
    "RC107": (1207.8, 11), "RC108": (1114.2, 10)
}

def run_benchmark(target_instances, data_dir="data", output_dir="result/benchmark_csv"):
    # 1. 准备输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 生成带时间戳的文件名，防止覆盖
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = os.path.join(output_dir, f"benchmark_{timestamp}.csv")
    
    # 2. 定义 CSV 表头 (按照你的要求排序)
    headers = [
        "Instance", 
        "Time",
        "Obj", "BKS_Obj", 
        "Gap_Pct", 
        "Trucks", "BKS_Trucks", 
        "Truck_Diff", 
    ]
    
    results = []
    
    print(f"🚀 Starting Benchmark on {len(target_instances)} instances...")
    print(f"📂 Reading data from: {data_dir}")
    print("-" * 60)

    # 3. 循环运行测试
    for name in target_instances:
        # 兼容处理：如果用户输入 "C101.txt" 或 "data/C101.txt"，自动提取 "C101"
        base_name = os.path.basename(name).split('.')[0]
        file_path = os.path.join(data_dir, f"{base_name}.txt")
        
        if not os.path.exists(file_path):
            print(f"❌ Error: File not found {file_path}")
            continue
            
        print(f"running {base_name}...", end=" ", flush=True)
        
        try:
            # --- 核心求解过程 ---
            # verbose=False 关闭求解器内部的大量打印，保持 Benchmark 界面整洁
            instance = VRPTWInstance(file_path, verbose=False)
            solver = CGSolver(instance, verbose=False) 
            
            start_time = time.perf_counter()
            obj, routes = solver.run()
            end_time = time.perf_counter()
            
            run_time = end_time - start_time
            num_trucks = len(routes)
            
            # --- BKS 对比计算 ---
            bks_obj, bks_trucks = SOLOMON_BKS.get(base_name, (0, 0))
            
            # Gap 计算 ( (Obj - BKS) / BKS )
            if bks_obj > 0:
                gap_pct = (obj - bks_obj) / bks_obj * 100
            else:
                gap_pct = 0.0
                
            truck_diff = num_trucks - bks_trucks if bks_trucks > 0 else 0
            
            # --- 记录数据 ---
            row = {
                "Instance": base_name,
                "Time": round(run_time, 2),
                "Obj": round(obj, 2),
                "BKS_Obj": bks_obj,
                "Gap_Pct": f"{gap_pct:.2f}%", # 格式化为百分比字符串
                "Trucks": num_trucks,
                "BKS_Trucks": bks_trucks,
                "Truck_Diff": truck_diff,
            }
                
            results.append(row)
            print(f"Done. (Obj: {obj:.2f}, Time: {run_time:.2f}s)")
            
        except Exception as e:
            print(f"Failed! Error: {e}")
            
    # 4. 写入 CSV
    if results:
        with open(csv_filename, mode='w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(results)
            
        print("-" * 60)
        print(f"✅ Benchmark Complete. Results saved to: {csv_filename}")
        print("-" * 60)
        # 简单打印表格预览
        print(f"{'Instance':<10} {'Obj':<10} {'BKS':<10} {'Gap':<10} {'Time':<10}")
        for r in results:
            print(f"{r['Instance']:<10} {r['Obj']:<10} {r['BKS_Obj']:<10} {r['Gap_Pct']:<10} {r['Time']:<10}")
    else:
        print("No results generated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run VRPTW Benchmark")
    
    # 允许命令行传入列表: python benchmark.py C101 C102 R101
    parser.add_argument('instances', metavar='N', type=str, nargs='*',
                        help='List of instance names (e.g., C101 R101)')
    
    args = parser.parse_args()
    
    # 如果命令行没有给参数，默认运行列表（你可以在这里手动修改默认测试集）
    target_list = args.instances
    if not target_list:
        target_list = ["C101", "C102","R101","R102"] # <--- 默认列表在这里改
        
    run_benchmark(target_list)