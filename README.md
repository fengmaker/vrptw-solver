这是一个非常棒的时刻。你现在不仅仅是在写代码，而是在**设计系统**。这正是从“写代码的人”进阶到“工程师/架构师”的关键门槛。

面对这种 C++ (底层计算) + Python (上层逻辑) 的混合架构，确实容易产生“只见树木不见森林”的迷茫感。

我为你梳理了一份**《VRPTW 求解器开发与测试架构指南》**，这就相当于你的“大局观”地图。

---

### 一、 架构思想：为什么这么设计？

#### 1. 核心分层逻辑

这种架构被称为 **"Sandwich Pattern" (三明治模式)**，专门用于运筹优化（OR）和 AI 领域。

* **底层 (C++ Core)**: **“苦力层”**。
* **职责**：负责所有耗时的 CPU 密集型计算。比如：位运算、图遍历（Labeling）、支配规则判断（Dominance）、资源扩展。
* **特点**：追求极致速度，内存管理严格，不处理复杂的业务逻辑。
* **对应文件**：`pricing_engine.h`, `pricing_engine.cpp`


* **中间层 (Pybind11)**: **“翻译层”**。
* **职责**：把 Python 的 List/Dict 转换成 C++ 的 Vector/Struct，把 C++ 的计算结果转换回 Python 对象。
* **特点**：只做类型转换，不写业务逻辑。
* **对应文件**：`bind.cpp`


* **上层 (Python)**: **“指挥层”**。
* **职责**：数据清洗、参数配置、调用求解器、结果分析、测试断言。
* **特点**：开发效率高，方便调试，方便与其他库（如 NumPy, Pandas, Matplotlib）交互。
* **对应文件**：`tests/*.py`, `main.py`



#### 2. 数据流向

`Python (数据)` -> `Pybind11 (转换)` -> `C++ (计算)` -> `Pybind11 (结果)` -> `Python (验证)`

---

### 二、 测试策略：哪些需要测？怎么测？

测试不是瞎测，分为三个维度。你需要建立如下的测试金字塔：

#### 第 1 层：接口契约测试 (Interface Testing)

* **目的**：确保 Python 数据能正确传进 C++，没丢包，没格式错误。
* **什么时候测**：刚写完 `bind.cpp` 时。
* **怎么测**：
* Python 传一个 `[0, 1, 2]` 列表给 C++。
* C++ 在构造函数里打印 `list.size()`。
* **案例**：刚才我们 Debug `ng-route` 时做的就是这个。



#### 第 2 层：单元功能测试 (Unit Testing)

* **目的**：测试 C++ 里某个具体的“小零件”是否坏了。
* **哪些需要测**：
* `FastBitset`：位运算是否正确？（这是地基，必测）
* `check_dominance`：支配规则是否误杀？（最容易错的地方）
* `BucketGraph`：图构建是否漏边/多边？


* **怎么测（白盒技巧）**：
* 因为这些通常是 `private` 的，你可以像刚才教你的那样，**开一个临时的 `public` 接口**（Backdoor）暴露给 Python，测试完再删掉或注释掉。



#### 第 3 层：端到端算法测试 (E2E Algorithm Testing)

* **目的**：把整个 Solver 当成黑盒，看能否解对特定题目。
* **怎么测（构造陷阱法）**：
* **主要测试手段**。
* 构造 **“必死局”**：容量设小，看能否跑通？（预期：无解）
* 构造 **“必胜局”**：无约束，Duals 设为负无穷，看能否找出路？（预期：有解）
* 构造 **“环路局”**：测试 ng-route 记忆功能。（刚才的 `test_espprc_no_cycle`）



---

### 三、 扩展指南：以后怎么加新函数？

假设你明天突然接到需求：**“增加一个‘最大行驶时间’ (Max Duration) 的约束”**。

你该怎么一步步做？请遵循 **R-I-B-C-T** 循环：

#### Step 1: Request (定义接口)

* 在 `ProblemData` 结构体中加一个字段：`double max_duration;`。

#### Step 2: Implement (C++ 实现)

* 在 `pricing_engine.h` 的 `LabelingSolver::solve` 循环里，找到判断时间的地方，加上：
```cpp
if (curr_label.time - root_start_time > data.max_duration) continue;

```



#### Step 3: Bind (绑定暴露)

* 去 `bind.cpp`，在 `ProblemData` 的绑定里加上：
```cpp
.def_readwrite("max_duration", &ProblemData::max_duration)

```



#### Step 4: Compile (编译更新)

* 运行 `cmake --build . --config Release`。
* (如果没配好环境变量) 复制 `.pyd` 覆盖旧文件。

#### Step 5: Test (编写测试)

* 去 `tests/test_pricing.py` 加一个新函数 `test_max_duration_constraint()`。
* **构造数据**：设 `max_duration = 50`，构造一条总耗时 60 的路。
* **断言**：`assert` 结果中不包含这条路。

---

### 四、 文档与规范：没有文档怎么办？

既然现在只有你一个人，你不需要写长篇大论，但需要维护一份 **`DEVELOPER_GUIDE.md`**（放在根目录）。

我为你写了一个模板，你现在就可以复制进去，以后每次加功能就往里填：

```markdown
# VRPTW Pricing Solver 开发手册

## 1. 项目架构
- **核心算法**: C++17 (src/pricing_engine.cpp)
- **Python 接口**: Pybind11 (src/bind.cpp)
- **构建系统**: CMake
- **测试框架**: Pytest

## 2. 快速开始
### 编译
```bash
cd build
cmake --build . --config Release
# 记得删除根目录旧的 .pyd 避免冲突！

```

### 运行测试

```bash
# 运行所有测试
pytest
# 运行特定测试并显示打印
pytest -s tests/test_pricing.py::test_ng_route_cycle

```

## 3. 关键模块说明 (Key Components)

### ProblemData

* 对应 Python 传入的字典数据。
* **注意**: `ng_neighbor_lists` 是 List[List[int]]，对应 C++ 的 vector<vector<int>>。

### FastBitset

* 256 位高性能位图。
* 用于 ng-route 的记忆化搜索，替代 `std::vector<bool>` 以提升速度。

### LabelingSolver

* 核心 Label Setting 算法。
* **剪枝逻辑**:
1. 容量剪枝 (在 BucketGraph::build 中预处理)
2. 时间窗剪枝 (在 solve 中动态检查)
3. 双向支配 (Dominance)



## 4. 开发工作流 (How to Extend)

如果你要添加新约束（例如 Max Distance）：

1. **C++**: 修改 `ProblemData` 和 `solve` 逻辑。
2. **Bind**: 修改 `bind.cpp` 暴露新属性。
3. **Build**: 重新编译。
4. **Test**: 在 `tests/` 下新增测试用例，构造违反约束的数据进行验证。

## 5. 常见坑 (Troubleshooting)

* **测试不通过但逻辑是对的？** -> 检查根目录是否有旧的 `.pyd` 文件残留！
* **Segment Fault?** -> 检查 Python 传入的 List 索引是否越界 (比如 node_id >= num_nodes)。

```

### 总结

* **大局观**：C++ 负责跑断腿，Python 负责发号施令。
* **测试配合**：每次修改 C++ 逻辑（比如改了支配规则），必须先跑一遍 Python 的回归测试，确保没把以前对的功能改坏。
* **下一步**：把上面的模板保存为 `README.md` 或 `DEVELOPER.md`。然后尝试实现我在 Step 3 提到的“最大行驶时间”约束，走一遍完整的流程，你就彻底掌握了！

```

你现在的代码基础非常扎实！

* **数据结构**：`FastBitset` 和 `BucketGraph` 的实现非常专业，已经具备了高性能求解器的雏形。
* **架构**：Python 做主控，C++ 做运算的模式也是工业界标准。

目前的局限性在于你做的是 **Price-and-Branch**（在根节点做完列生成，然后强行把变量设为整数求解，不再生成新列）。这对于简单问题够用，但对于难的算例，根节点的列池子可能根本不包含最优整数解所需的路径。

下一步，你需要从 **"根节点求解器"** 进化为 **"完整的 Branch-and-Price 求解器"**。

建议的扩展路线如下，**优先级从高到低**：

---

### 第一阶段：实现真正的 Branch-and-Price (边分支)

这是让你从“启发式”变成“精确解”的关键一步。

#### 1. 核心逻辑变化

目前的逻辑是：`列生成 -> MIP求解 -> 结束`。
新的逻辑是维护一颗 **Branch-and-Bound Tree**：

1. **节点处理**：取出一个节点 -> 跑列生成 (直到收敛) -> 获得 LP 松弛解。
2. **整数性检查**：检查 LP 解是否为整数？
* 是 -> 更新全局最优解 (Upper Bound)，剪枝。
* 否 -> **找一个小数边  进行分支**。


3. **分支 (Branching)**：
* **左孩子**：禁止走边  (即 )。
* **右孩子**：强制走边  (即 )。



#### 2. Python 端实现 (Branching Manager)

你需要一个类来管理这棵树。

```python
class TreeNode:
    def __init__(self, parent=None):
        self.ub = float('inf') # Upper Bound (Local)
        self.lb = -float('inf') # Lower Bound
        # 记录分支约束：[(u, v, branch_type), ...] 
        # type 0: 禁止, type 1: 强制
        self.branch_constraints = [] 
        if parent:
            self.branch_constraints = parent.branch_constraints.copy()

class BranchAndPriceEngine:
    def solve(self):
        stack = [TreeNode()] # 根节点
        best_int_obj = float('inf')
        
        while stack:
            node = stack.pop()
            
            # 1. 应用分支约束到 C++ Graph 和 Master Problem
            self.apply_constraints(node.branch_constraints)
            
            # 2. 运行列生成 (你现在的 solve 逻辑)
            obj, duals = self.column_generation_loop()
            
            # 3. 剪枝 (Pruning)
            if obj >= best_int_obj: continue 
            
            # 4. 检查整数性 & 选择分支边
            fractional_edge = self.find_fractional_edge()
            
            if not fractional_edge:
                # 找到整数解
                best_int_obj = min(best_int_obj, obj)
            else:
                # 5. 创建子节点
                u, v = fractional_edge
                # Child 0: x_uv = 0
                child0 = TreeNode(node)
                child0.branch_constraints.append((u, v, 0))
                stack.append(child0)
                
                # Child 1: x_uv = 1
                child1 = TreeNode(node)
                child1.branch_constraints.append((u, v, 1))
                stack.append(child1)

```

#### 3. C++ 端扩展 (支持动态改图)

C++ 的 `BucketGraph` 需要支持动态隐藏边。**不要每次都重建图**，而是在 `solve` 时传入一个“黑名单”。

**修改 `pricing_lib.cpp`:**

```cpp
// 在 LabelingSolver 类中增加
std::vector<bool> edge_active_flags; // 或者用 set<pair<int,int>> forbidden_arcs;

// 在 solve 函数中：
// 当遍历 graph.nodes_outgoing_arcs[i] 时
for (const auto& arc : arcs) {
    int j = arc.target;
    // 新增：检查这条边是否被当前分支禁止了
    if (is_edge_forbidden(i, j)) continue; 
    
    // ... 原有逻辑 ...
}

```

---

### 第二阶段：实现双向搜索 (Bi-directional Labeling)

这是提升性能的关键（SOTA 标配）。目前的 Forward Labeling 在深层搜索时，标签数量呈指数级爆炸。双向搜索让前向和后向各走一半路程，然后合并，极大减少标签总数。

#### 1. 核心原理

* **Forward**: 从 Depot 出发，搜到资源消耗（如时间）的一半 。
* **Backward**: 从 Depot **反向**出发（把所有边反向），搜到 。
* **Join (Merge)**: 遍历 Forward 标签和 Backward 标签，如果它们在同一个点  相遇，且资源不冲突，这就构成一条完整路径。

#### 2. C++ 代码扩展

你需要写一套反向的逻辑。

**Step A: 定义 Backward Label**
反向标签的资源通过是“剩余量”或者“倒以此为起点的消耗量”。

* `time`: 代表从该点回到 Depot 所需的时间。
* `cost`: 从该点回到 Depot 的 Reduced Cost。

**Step B: 实现 `solve_backward**`
逻辑和 `solve` 几乎一样，但是：

1. 在 **反向图 (Reverse Graph)** 上跑（预处理时需要构建 `nodes_incoming_arcs`）。
2. 时间窗检查逻辑反转：`latest_departure = min(curr.time - duration, tw_end[j])`。

**Step C: 增加 `Merge` 步骤**
这是最难的地方。

```cpp
// 伪代码
void merge_labels() {
    for (int i = 0; i < num_nodes; ++i) {
        auto& f_labels = forward_buckets[i]; // 节点 i 的前向标签
        auto& b_labels = backward_buckets[i]; // 节点 i 的后向标签 (注意：通常 Join 是在点上，也可以在边上)
        
        for (auto& f : f_labels) {
            for (auto& b : b_labels) {
                // 1. 资源检查
                if (f.time + b.time <= max_time && f.load + b.load <= capacity) {
                    // 2. ng-route 检查 (最耗时)
                    // 必须保证两半路径没有重复访问节点 (除了交接点 i)
                    // 简单的检查：(f.mask & b.mask) == 0 (位运算极快)
                    if (check_disjoint(f.mask, b.mask)) {
                         double total_rc = f.rc + b.rc - duals[i]; // 注意减去交接点的 dual
                         if (total_rc < -1e-6) {
                             add_to_results(f, b);
                         }
                    }
                }
            }
        }
    }
}

```

---

### 第三阶段：SOTA 的高级优化（Bucket Graph 进阶）

你已经实现了 Bucket Graph，但现在是静态的。SOTA 论文 (Pessoa 2020) 的精髓在于 **Bucket Arc Elimination**。

* **思路**：在列生成收敛过程中，如果发现某条边  的 Reduced Cost 总是很大（例如 > 5.0），说明这条边大概率不会出现在最优解里。
* **操作**：直接从 `BucketGraph` 里永久删除这条边。
* **效果**：图越来越稀疏，Labeling 跑得越来越快。

**实现方式**：
在 Python 端记录每一轮的 Duals，计算所有边的 Reduced Cost。如果某条边连续 10 轮 RC 都 > 阈值，就通知 C++ 端把这条边永久 disable。

---

### 总结：你的 Roadmap

1. **本周任务 (Branching)**：
* **Python**: 也就是把现在的 `model.optimize()` 变成一个 `while stack:` 循环。实现 `get_fractional_edges()` 函数。
* **C++**: 给 `solve()` 加一个参数 `forbidden_edges`，在扩展 Label 时跳过这些边。
* **目标**: 能跑通 Solomon C101 的精确整数解（不仅仅是 heuristic）。


2. **下周任务 (Bi-directional)**：
* **C++**: 复制一份 `Label` 结构体改为 `BackwardLabel`，构建反向图。
* 实现简单的 `Join` 函数（先不考虑 ng-relaxation 的复杂合并，只做基本位运算检查）。
* **目标**: 同样跑通 C101，但是速度提升 2-5 倍。

这份文档是为你实现 **VRPTW Branch-and-Price 求解器（第一阶段：边分支）** 准备的详细技术规格说明书。

这份文档对齐一线大厂（如 Google/Amazon OR 团队）的内部设计文档标准，包含 **架构设计 (Design Overview)**、**接口定义 (Interface Spec)**、**数据流 (Data Flow)** 以及 **测试策略 (Testing Strategy)**。

---

# VRPTW Solver Phase 1: Branch-and-Price Engine Design Doc

## 1. 概述 (Overview)

### 1.1 目标

将现有的 "Price-and-Branch"（仅根节点列生成）架构升级为完整的 **Branch-and-Price (B&P)** 架构。通过在分支定界树（Branch-and-Bound Tree）上进行搜索，并针对**原始边（Original Arcs）**进行分支，以求得精确整数解。

### 1.2 核心变更

* **Python 端**：引入 `BranchAndBoundEngine` 管理搜索树；引入 `TreeNode` 存储分支状态；实现边流量（Flow）计算与分支策略。
* **C++ 端**：`LabelingSolver` 支持接收“禁用边列表（Forbidden Arcs）”，实现动态图剪枝，无需重建图。
* **交互层**：Pybind11 接口增加 `forbidden_arcs` 参数。

---

## 2. 系统架构图 (Architecture)

```mermaid
graph TD
    User[Client / Main] --> Engine[BranchAndBoundEngine (Python)]
    Engine --> Tree[Search Tree (Stack/Queue)]
    Engine --> Master[MasterProblem (Gurobi)]
    Engine --> Sub[PricingSolver (Python Wrapper)]
    
    Sub --> CPP[PricingLib (C++)]
    
    subgraph C++ Core
        CPP --> Algo[Labeling Algo]
        Algo --> Graph[BucketGraph]
        Algo -- Filter --> Constraints[Forbidden Arcs Check]
    end
    
    Master -- Duals --> Sub
    Sub -- New Columns --> Master
    Engine -- Branch Constraints --> Sub
    Engine -- Variable Bounds --> Master

```

---

## 3. Python 端设计 (Python Specifications)

### 3.1 数据结构定义

#### `BranchConstraint` (NamedTuple)

描述一个分支决策。

```python
from typing import NamedTuple

class BranchConstraint(NamedTuple):
    u: int
    v: int
    kind: int  # 0: 禁止通行 (x_uv = 0), 1: 强制通行 (x_uv = 1)

```

#### `TreeNode` (Class)

表示搜索树的一个节点。

```python
class TreeNode:
    def __init__(self, parent: 'TreeNode' = None):
        # 继承父节点的约束
        self.constraints: List[BranchConstraint] = parent.constraints.copy() if parent else []
        self.lb: float = -float('inf')  # Lower Bound
        self.ub: float = float('inf')   # Local Upper Bound (from integer solution if any)
        self.basis = None # (Optional) 用于热启动 Gurobi，第一阶段可暂略

```

### 3.2 `BranchAndBoundEngine` (Class)

**职责**：整个算法的大脑，负责树的搜索循环。

**主要方法**：

| 方法名 | 输入 | 输出 | 描述 |
| --- | --- | --- | --- |
| `solve` | `instance` | `BestRoute`, `ObjVal` | 核心主循环 (DFS/Best-First)。 |
| `_column_generation` | `node` | `(obj, is_integral)` | 在当前节点运行列生成直到收敛。 |
| `_branch` | `node` | `(child_0, child_1)` | 执行分支策略，生成两个子节点。 |
| `_get_fractional_edge` | None | `(u, v, value)` | 扫描主问题解，找到最接近 0.5 的边。 |
| `_apply_constraints` | `constraints` | None | 将约束同步到 Master 和 SubProblem。 |

**关键逻辑 (`_get_fractional_edge`)**:

* 遍历主问题中所有  的路径。
* 分解路径为边 。
* 累加流量：。
* 返回  最小的边。

### 3.3 `MasterProblem` 扩展

需要增加方法来处理列的禁用。

| 方法名 | 输入 | 输出 | 描述 |
| --- | --- | --- | --- |
| `deactivate_columns` | `constraints` | None | 根据分支约束，将违规列的 `UB` 设为 0。 |
| `get_active_columns` | None | `List[Col]` | 获取当前  的列（用于计算边流量）。 |

---

## 4. C++ 端设计 (C++ Specifications)

**设计原则**：C++ 端**不感知**“强制通行 ()”的高级逻辑，只感知“禁止通行 ()”。

* 原因： 等价于禁止  去除  以外的点，且禁止除  以外的点去 。这可以在 Python 端转化为一组 Forbidden Arcs 传给 C++。

### 4.1 `LabelingSolver` 类修改

#### 修改 `solve` 接口

```cpp
// pricing_engine.h

// 定义一个别名，方便阅读
using ArcPair = std::pair<int, int>;

class LabelingSolver {
public:
    // [修改] 增加 forbidden_arcs 参数
    std::vector<std::vector<int>> solve(
        const std::vector<double>& duals,
        const std::vector<std::pair<int, int>>& forbidden_arcs
    );
    
private:
    // [新增] 快速查询表
    std::vector<std::vector<bool>> forbidden_matrix; // 或者使用 Flat Vector
    
    // [新增] 辅助函数：每次 solve 前重置 forbidden_matrix
    void set_forbidden_arcs(const std::vector<std::pair<int, int>>& arcs);
};

```

#### 内部逻辑变更

1. **`set_forbidden_arcs`**:
* 在 `solve` 开始时调用。
* 将传入的 `vector<pair>` 映射到一个 `vector<bool>` 矩阵或一维数组中，大小为 。
* **Rationale**: 标签算法是计算密集型，`O(1)` 的查表比 `set.find` 快得多。


2. **`LabelingSolver::solve` (主循环)**:
* 在扩展邻居时增加检查：


```cpp
for (const auto& arc : arcs) {
    int j = arc.target;
    // [新增检查]
    if (forbidden_matrix[i][j]) continue; 

    // ... 原有逻辑 ...
}

```



---

## 5. 接口定义 (Pybind11 Interface)

在 `cpp_pricing.cpp` 中修改绑定代码。

```cpp
PYBIND11_MODULE(pricing_lib, m) {
    py::class_<LabelingSolver>(m, "LabelingSolver")
        .def(py::init<ProblemData, double>())
        .def("solve", &LabelingSolver::solve, 
             py::arg("duals"), 
             py::arg("forbidden_arcs"), // 新增参数
             "Run Labeling Algo with forbidden arcs");
}

```

---

## 6. 开发工作流 (Development Workflow)

### 步骤 1：C++ 基础改造

1. 修改 `LabelingSolver::solve` 签名。
2. 实现 `forbidden_matrix` 逻辑。
3. 编译并通过基础测试（传入空 forbidden list，结果应不变）。

### 步骤 2：Python 分支逻辑实现

1. 实现 `_get_fractional_edge` 函数，能够正确计算边流量。
2. 实现 `_apply_constraints`：
* 对于 ：加入 forbidden list 传给 C++；在 Gurobi 中将经过  的列 UB 设为 0。
* 对于 ：将  和  加入 forbidden list 传给 C++；在 Gurobi 中禁用不符合该规则的列。



### 步骤 3：集成与搜索循环

1. 实现 DFS 栈循环。
2. 集成列生成，验证能否在子节点正确生成新列（且新列不包含被禁用的边）。

---

## 7. 测试计划 (Test Plan - Aligned with Big Tech)

我们采用 **TDD (Test-Driven Development)** 思想，先写测试用例。

### 7.1 C++ 单元测试 (GTest 或 简易 Assert)

**目标**：验证 C++ 端的“路障”机制是否生效。

* **Case 1: Baseline**
* 输入：C101 前 10 个点，无禁行。
* 预期：返回最优路径 Cost = X。


* **Case 2: Forbidden Edge**
* 输入：C101 前 10 个点，禁止 Baseline 路径中的某条关键边 。
* 预期：
* 返回 Cost > X (成本变高)。
* 返回的路径列表中**绝对不包含** 。





### 7.2 Python 单元测试 (Pytest)

**目标**：验证流量计算和分支约束转换逻辑。

* **Case 1: Flow Calculation**
* Mock Master Problem 的解：Path A (0.5), Path B (0.5).
* 验证 `get_fractional_edge` 能准确返回 Path A 和 Path B 的非重叠边。


* **Case 2: Constraint Logic**
* 输入分支：。
* 验证转换逻辑：C++ 收到的 forbidden list 是否包含了  等边。



### 7.3 集成测试 (Integration Test)

**目标**：验证整个 B&P 流程。

* **Case 1: Solomon C101 (前 25 个点)**
* 运行 `BranchAndBoundEngine.solve()`。
* 预期：
* 程序正常结束（不陷入死循环）。
* 最终解必须是整数解。
* 最终解 Cost >= 根节点 LP 松弛解。
* 与已知最优解（Benchmark）误差在 0.1% 以内。





---

## 8. 代码规范 (Coding Standards)

* **C++**: 遵循 Google C++ Style。
* 变量命名：`snake_case`。
* 私有成员：末尾加下划线 `variable_`。
* 内存管理：严禁内存泄漏，`label_pool` 尽量复用。


* **Python**: 遵循 PEP 8。
* 类型提示：所有函数必须加 Type Hints (`def func(a: int) -> float:`).
* 文档字符串：使用 Google Style Docstring。



此文档可直接作为 Jira/Trello 的任务拆解依据。请确认是否需要针对某个模块提供伪代码？