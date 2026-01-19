from encodings.punycode import T
import os
import time
from src.instance import VRPTWInstance
from src.solver import CGSolver
from src.visualizer import plot_solution

if __name__ == "__main__":
    # 配置
    DATA_PATH = "data/C103.txt" # 数据文件路径
    TEST_SIZE = 20 # 跑全量
    
    if not os.path.exists(DATA_PATH):
        print(f"Error: File not found at {DATA_PATH}")
        exit(1)

    # 1. 加载数据
    instance = VRPTWInstance(DATA_PATH,verbose=True) # 去掉 max_customers 跑全量
    
    # 2. 初始化求解器
    solver = CGSolver(instance,verbose=True)
    
    # 3. 运行列生成
    start_time = time.perf_counter()
    
    # 4. 求解整数解 (获取清洗后的距离和路径)
    integer_dist, final_routes = solver.run()
    
    end_time = time.perf_counter()
    
    # 5. 打印最终总结
    print("\n" + "="*40)
    print(f"INSTANCE: {DATA_PATH}")
    print(f"STATUS  : Optimal Integer Solution Found")
    print(f"VEHICLES: {len(final_routes)}")
    print(f"DISTANCE: {integer_dist:.2f}")
    print(f"TIME    : {end_time - start_time:.4f} s")
    print("="*40)
    ins_name = DATA_PATH.split('/')[-1].split('.')[0]
    # 6. 可视化
    if final_routes:
        chart_title = f"{ins_name}: Optimal Integer Solution: {len(final_routes)} Vehicles, Dist {integer_dist:.2f}"
        plot_solution(instance, final_routes, title=chart_title)