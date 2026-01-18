import os
import matplotlib.pyplot as plt
from datetime import datetime

def plot_solution(instance, routes, title="VRPTW Solution"):
    """
    绘制 VRPTW 路线图并保存到 result 文件夹，文件名包含时间戳
    """
    plt.figure(figsize=(12, 10))
    
    # 1. 绘制底图 (客户点和仓库)
    xc = [c.x for c in instance.customers]
    yc = [c.y for c in instance.customers]
    
    plt.scatter(xc[1:], yc[1:], c='grey', s=30, alpha=0.6, label='Customers')
    plt.scatter(xc[0], yc[0], c='red', marker='s', s=100, zorder=10, label='Depot')
    
    # 2. 绘制路径
    cmap = plt.get_cmap('tab20')
    
    for i, path in enumerate(routes):
        path_x = [instance.customers[node].x for node in path]
        path_y = [instance.customers[node].y for node in path]
        color = cmap(i % 20)
        
        plt.plot(path_x, path_y, color=color, linewidth=1.5, alpha=0.8, label=f'Vehicle {i+1}')

    # 3. 设置图表格式
    plt.title(title, fontsize=16, fontweight='bold', pad=20)
    plt.xlabel("X Coordinate")
    plt.ylabel("Y Coordinate")
    plt.grid(True, linestyle='--', alpha=0.5)
    
    # 图例逻辑
    if len(routes) <= 10:
        plt.legend(loc='best', fontsize='small', frameon=True)
    else:
        handles, labels = plt.gca().get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        # 仅显示 Depot 和 Customers，防止图例过长
        if 'Depot' in by_label and 'Customers' in by_label:
            plt.legend([by_label['Depot'], by_label['Customers']], 
                       ['Depot', 'Customers'], loc='upper right')

    plt.tight_layout()
    
    # ---------------------------------------------------------
    # 4. 保存文件
    # ---------------------------------------------------------
    
    # 定义保存目录
    save_dir = "result"
    
    # 如果目录不存在，自动创建
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        print(f"Created directory: {save_dir}")
        
    # 生成时间戳: YYYYMMDD_HHMMSS (例如: 20231027_153005)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 拼接文件名: result/solution_20231027_153005.png
    filename = f"solution_{timestamp}.png"
    filepath = os.path.join(save_dir, filename)
    
    print(f"Saving solution plot to: {filepath}")
    plt.savefig(filepath, dpi=300)
    
    # 显示图片
    plt.show()