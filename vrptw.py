import math
import gurobipy as gp
from gurobipy import GRB
import sys
import os
import time
# ==========================================
# 1. 数据读取模块 (Solomon Format Parser)
# ==========================================

def read_solomon_instance(filepath, max_customers=None):
    """
    读取 Solomon 格式的文本文件。
    max_customers: 用于测试，如果只想跑前 25 个点，可以传 25。传 None 读取所有。
    """
    nodes = []
    capacity = 0
    
    print(f"正在读取数据文件: {filepath} ...")
    
    with open(filepath, 'r') as f:
        lines = f.readlines()

    section = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith("VEHICLE"):
            section = "VEHICLE"
            continue
        elif line.startswith("CUSTOMER"):
            section = "CUSTOMER"
            continue
            
        # 解析车辆容量
        if section == "VEHICLE":
            # 这一行通常是 "NUMBER     CAPACITY"
            if line.startswith("NUMBER"): 
                continue
            parts = line.split()
            if len(parts) >= 2:
                # Solomon 格式第一列是车辆数，第二列是容量
                capacity = int(parts[1])
                print(f"  -> 车辆容量检测为: {capacity}")
            section = None # 读完这就完了
            
        # 解析客户数据
        elif section == "CUSTOMER":
            # 这一行通常是表头 "CUST NO.  XCOORD. ..."
            if line.startswith("CUST") or not line[0].isdigit():
                continue
                
            parts = line.split()
            # Solomon 格式: [0:ID, 1:X, 2:Y, 3:Demand, 4:Ready, 5:Due, 6:Service]
            cust = {
                'id': int(parts[0]),
                'x': float(parts[1]),
                'y': float(parts[2]),
                'dem': int(parts[3]),
                'tw_a': int(parts[4]),
                'tw_b': int(parts[5]),
                'serv': int(parts[6])
            }
            
            # 如果有限制测试规模
            if max_customers is not None and len(nodes) > max_customers:
                break
                
            nodes.append(cust)

    print(f"  -> 成功读取 {len(nodes)} 个节点 (含 Depot)。")
    return nodes, capacity
# 你的数据文件路径
DATA_PATH = "data/C101.txt"

# ⚠️ 关键设置：
# C101 有 100 个点。直接跑精确算法（没有 ng-route 和强力割平面）可能会非常慢或内存爆炸。
# 建议先只切前 25 个点或是 50 个点来测试代码正确性。
TEST_SIZE = 10  # 设为 None 则跑全量 100 点 (慎重！)

if not os.path.exists(DATA_PATH):
    print(f"错误：找不到文件 {DATA_PATH}")
    sys.exit(1)

# 加载数据
nodes, CAPACITY = read_solomon_instance(DATA_PATH, max_customers=TEST_SIZE)
N = len(nodes)

# 预计算距离矩阵 (欧几里得距离)
dist_matrix = [[0.0] * N for _ in range(N)]
for i in range(N):
    for j in range(N):
        d = math.sqrt((nodes[i]['x']-nodes[j]['x'])**2 + (nodes[i]['y']-nodes[j]['y'])**2)
        dist_matrix[i][j] = round(d, 1) # Solomon 标准通常保留一位小数或不保留，这里沿用之前的习惯

# ==========================================
# 2. 标签类 (传统写法)
# ==========================================
class MasterProblem:
    def __init__(self, num_customers):
        self.num_customers = num_customers
        self.model = gp.Model("VRPTW_Master")
        # 建议先打开输出，方便调试，等稳定了再关掉 (设为 1)
        self.model.setParam('OutputFlag', 1) 
        
        self.routes = [] 
        
        self.constrs = {}
        # --- 1. 初始化约束 ---
        # 覆盖约束 (Covering Constraints): 每个客户至少被服务一次
        # sum(a_ir * lambda_r) >= 1
        for i in range(1, num_customers):
            # [修正] 使用 LinExpr() 创建一个空的线性表达式对象
            # 这样 Gurobi 就知道这是一个 "0.0 * x + ... >= 1" 的待填充约束
            self.constrs[i] = self.model.addConstr(gp.LinExpr() >= 1, name=f"cover_{i}")

        # --- 2. 初始化变量 (Dummy Initialization) ---
        # 为了防止一开始模型“不可行 (Infeasible)”，我们必须放入一些“保底路径”。
        # 最简单的保底：每个客户派一辆专车 (0 -> i -> 0)，成本设为无穷大。
        # 这样模型一定有解，但通过列生成，我们会慢慢把这些昂贵的废路径替换掉。
        self.init_dummy_columns()

    def init_dummy_columns(self):
        """添加 Big-M 的初始列，保证模型可行"""
        big_m_cost = 10000.0
        for i in range(1, self.num_customers):
            # 创建一条虚拟路径: 0 -> i -> 0
            # 这条路径只服务客户 i
            col = gp.Column()
            col.addTerms(1.0, self.constrs[i]) # 在第 i 个约束上的系数是 1
            
            # 添加变量 lambda_dummy_i
            self.model.addVar(obj=big_m_cost, vtype=GRB.CONTINUOUS, column=col, name=f"dummy_{i}")
            self.routes.append(f"Dummy {i}")

    def solve(self):
        """求解当前的 RMP，返回对偶值"""
        self.model.optimize()
        
        # [新增] 状态检查
        if self.model.Status == GRB.INFEASIBLE:
            print("!!! 错误：主问题不可行 (Infeasible) !!!")
            # 强制计算不可行原因 (IIS)，帮助你看到底哪个约束出了问题
            self.model.computeIIS()
            self.model.write("model_infeasible.ilp")
            print("已生成 model_infeasible.ilp，请查看冲突约束。")
            return float('inf'), []
            
        if self.model.Status != GRB.OPTIMAL:
            print(f"!!! 警告：主问题未达到最优，状态码: {self.model.Status} !!!")
            return float('inf'), []

        # 获取对偶值
        duals = [0.0] * self.num_customers
        for i in range(1, self.num_customers):
            duals[i] = self.constrs[i].Pi
            
        return self.model.ObjVal, duals

    def add_route(self, route_label):
        """将子问题找到的新路径加到主问题里"""
        path = route_label.get_path()
        cost = route_label.cost # 注意：这里我们要加的是"物理Cost"，不是Reduced Cost!
        
        # 修正：子问题里的 label.cost 是 Reduced Cost。
        # 我们需要重新算一下这条路的 物理 Cost。
        # (简单起见，我这里重新算一遍物理距离，实际代码里应该在 Label 里存两个 Cost)
        physical_cost = 0.0
        for k in range(len(path)-1):
            u, v = path[k], path[k+1]
            # 这里引用你之前的 dist_matrix
            physical_cost += dist_matrix[u][v]
            
        # 构建 Gurobi 的 Column 对象
        col = gp.Column()
        for node_idx in path:
            if node_idx != 0: # 只有客户节点对应约束
                col.addTerms(1.0, self.constrs[node_idx])
        
        # 添加变量
        var_name = f"route_{len(self.routes)}"
        self.model.addVar(obj=physical_cost, vtype=GRB.CONTINUOUS, column=col, name=var_name)
        
        # 记录路径信息
        self.routes.append(path)

class Label:
    def __init__(self, current_node, cost, time, load, visited_mask, parent=None):
        """
        显式初始化所有属性
        """
        self.current_node = current_node  # 当前所在的点 ID
        self.cost = cost                  # 累积的 Reduced Cost
        self.time = time                  # 当前时间
        self.load = load                  # 当前载重
        self.visited_mask = visited_mask  # 访问过的点（二进制掩码）
        self.parent = parent              # 上一个标签（用于回溯路径）

    def get_path(self):
        """回溯获取完整路径"""
        path = []
        curr = self
        while curr is not None:
            path.append(curr.current_node)
            curr = curr.parent
        return path[::-1] # 反转列表，变成 [0, 3, 1...]

    def __repr__(self):
        """
        为了打印好看，否则 print(L1) 会显示 <__main__.Label object at 0x...>
        """
        return f"Label(node={self.current_node}, cost={self.cost:.2f}, time={self.time:.1f}, load={self.load})"

# ==========================================
# 3. 资源扩展函数 (REF) - 物理引擎核心
# ==========================================
def extend(label, to_node_idx, duals):
    """
    尝试从 label.current_node 走到 to_node_idx。
    如果不可行（超时、超载、回路），返回 None。
    否则返回新的 Label 对象。
    """
    i = label.current_node
    j = to_node_idx
    # 1. 检查回路 (Elementary Check)
    # 逻辑：如果 j 的位置在二进制 mask 里是 1，说明去过了
    if j != 0 and (label.visited_mask & (1 << j)):
        return None

    # 2. 资源更新：容量
    new_load = label.load + nodes[j]['dem']
    if new_load > CAPACITY:
        return None  # 超载

    # 3. 资源更新：时间
    # 到达时间 = 上一节点出发时间 + 服务时间 + 行驶时间
    arrival_time = label.time + nodes[i]['serv'] + dist_matrix[i][j]
    # 时间窗逻辑：如果早到，就等待；如果晚到，就非法
    start_time = max(arrival_time, nodes[j]['tw_a'])
    
    if start_time > nodes[j]['tw_b']:
        return None  # 超时

    # 4. 资源更新：成本 (Reduced Cost)
    # cost = 旧cost + (距离 - j点的对偶奖励)
    # 注意：depot(点0)通常没有对偶值，或者为0
    reduced_cost_step = dist_matrix[i][j] - duals[j]
    new_cost = label.cost + reduced_cost_step

    # 5. 更新访问掩码
    # 用 "按位或" 运算把 j 的位置标为 1
    new_mask = label.visited_mask | (1 << j)

    # 返回一个新的 Label 对象
    return Label(
        current_node=j,
        cost=new_cost,
        time=start_time,
        load=new_load,
        visited_mask=new_mask,
        parent=label
    )
    
def is_dominated(new_label, existing_labels):
    """
    检查 new_label 是否被 existing_labels 里的任何一个旧标签支配。
    如果是，返回 True (代表 new_label 是垃圾，应该丢弃)。
    """
    for old in existing_labels:
        # 1. 检查是否在同一个点 (这是前提)
        if old.current_node != new_label.current_node:
            continue
            
        # 2. 核心支配逻辑 (Dominance Logic)
        # 如果 old 在所有维度上都 <= new，那么 new 就被支配了
        
        # 成本更低 (注意：这里要考虑到浮点数误差，通常用一个极小量 EPS)
        condition_cost = (old.cost <= new_label.cost + 1e-6)
        
        # 时间更早
        condition_time = (old.time <= new_label.time + 1e-6)
        
        # 载重更小
        condition_load = (old.load <= new_label.load)
        
        # 访问过的节点是子集 (S_old ⊆ S_new)
        # 位运算技巧： (A & B) == A 说明 A 的所有 1，B 都有。
        condition_subset = ((old.visited_mask & new_label.visited_mask) == old.visited_mask)
        
        if condition_cost and condition_time and condition_load and condition_subset:
            return True # new_label 没有任何存在的价值
            
    return False

def solve_pricing(duals):
    """
    求解子问题：找到 Reduced Cost 最负的路径。
    """
    # 1. 初始化
    # 存放所有待扩展的标签 (Queue)
    unprocessed_labels = []
    
    # 存放每个节点上保留下来的“精英标签” (用于支配检查)
    # 结构: node_labels[i] = [Label1, Label2...]
    node_labels = [[] for _ in range(N)]
    
    # 创建初始标签 (Depot)
    L0 = Label(0, 0.0, 0.0, 0, 1)
    unprocessed_labels.append(L0)
    node_labels[0].append(L0)
    
    # 用于记录找到的完整回路标签 (回到 Depot 的)
    final_routes = []

    # 2. 主循环
    while unprocessed_labels:
        # 取出一个标签 (这里用 pop(0) 相当于 BFS，也可以用 pop() 相当于 DFS)
        current_label = unprocessed_labels.pop(0)
        
        # 如果当前标签已经被后来者支配了（这种情况在严谨实现里可能发生），跳过
        # 这里简化处理，暂不再次检查
        
        # 尝试向所有节点扩展
        for next_node in range(N):
            # 扩展逻辑 (Physics)
            new_label = extend(current_label, next_node, duals)
            
            # 如果扩展失败 (Infeasible)，跳过
            if new_label is None:
                continue
            
            # 如果回到了 Depot (next_node == 0)
            if next_node == 0:
                final_routes.append(new_label)
                continue
            
            # --- 关键：支配检查 (Algorithm) ---
            # 如果新标签被已有的标签支配，丢弃它
            if is_dominated(new_label, node_labels[next_node]):
                continue
            
            # 如果新标签存活下来了：
            # (进阶优化：其实新标签也可能支配旧标签，应该把旧标签删掉。为了代码简单，这里先不做删除)
            
            node_labels[next_node].append(new_label)
            unprocessed_labels.append(new_label)

    # 3. 筛选结果
    # 我们只关心回到 Depot 且 Reduced Cost < 0 的路径
    negative_cost_routes = [L for L in final_routes if L.cost < -1e-6]
    
    # 按 cost 排序，最负的排前面
    negative_cost_routes.sort(key=lambda x: x.cost)
    
    return negative_cost_routes

def run_column_generation():
    print("=== 开始列生成 (Column Generation) ===")
    
    # 1. 初始化主问题
    master = MasterProblem(num_customers=N)
    
    iteration = 0
    while True:
        iteration += 1
        
        # 2. 求解 RMP，拿到对偶值
        obj_val, duals = master.solve()
        print(f"Iter {iteration}: RMP Objective = {obj_val:.2f}")
        # print(f"   Duals: {[round(d,1) for d in duals]}")
        
        # 3. 调用子问题 (Pricing)
        # 注意：solve_pricing 里的 Reduced Cost 计算依赖于 duals
        # 我们要找 Reduced Cost < 0 的路径
        new_routes = solve_pricing(duals)
        
        # 4. 检查停止条件
        # 如果没有负 RC 的路径，说明当前解已经是 LP 最优了
        if not new_routes:
            print(">>> 没有发现负 Reduced Cost 路径。列生成收敛！")
            break
            
        # 5. 添加列 (Add Columns)
        # 策略：可以只加最好的一条，也可以加多条。通常加所有负的收敛更快。
        print(f"   >>> 发现了 {len(new_routes)} 条新路径，加入主问题...")
        
        min_rc = new_routes[0].cost
        print(f"   >>> Best Reduced Cost: {min_rc:.2f}")
        
        # 这里我们只加最负的那一条 (Rank 1)，你可以改为加前 5 条试试
        for route in new_routes:
             if route.cost < -0.001: # 再次过滤一下精度误差
                 master.add_route(route)
        
    print("\n=== 最终结果 ===")
    print(f"最优 LP 目标函数值: {master.model.ObjVal:.2f}")
    
    # 打印选中的变量 (只打印 > 0.001 的，因为是 LP 松弛解，可能是小数)
    for v in master.model.getVars():
        if v.x > 0.001:
            print(f"变量 {v.VarName} = {v.x:.2f}")
            # 如果是 route_xx，你需要去 master.routes 列表里查具体路径
    print("\n=== 最终方案详情 ===")
    for v in master.model.getVars():
        if v.x > 0.001:
            # 变量名类似于 "route_4", "dummy_1"
            if v.VarName.startswith("route_"):
                # 解析索引：从 "route_4" 提取出 4
                route_idx = int(v.VarName.split("_")[1])
                # 从 master.routes 列表里拿到真实的路径列表
                real_path = master.routes[route_idx]
                print(f"变量 {v.VarName} (选了 {v.x:.1f} 次): 路径 {real_path}")
                
                # 顺便算一下这条路的物理成本验证一下
                cost = 0
                for k in range(len(real_path)-1):
                    cost += dist_matrix[real_path[k]][real_path[k+1]]
                print(f"    -> 物理成本验证: {cost:.2f}")
            
            elif v.VarName.startswith("dummy_"):
                print(f"警告：虚拟路径 {v.VarName} 依然存在！说明原问题可能有不可行的点。")

if __name__ == "__main__":
    # 确保前面的 dist_matrix, solve_pricing 等都已定义
    print(f"当前测试规模: {N-1} 个客户 (总节点数 {N})")
    # --- 计时开始 ---
    start_time = time.perf_counter()
    run_column_generation()
    # --- 计时结束 ---
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    
    print(f"\n" + "="*30)
    print(f"总运行时间: {elapsed_time:.4f} 秒")
    print(f"="*30)