你好！我是 **OR-Architect**。很高兴看到你已经搭建起了一个基于 C++ 扩展和 Bitset 优化的 VRPTW 定价求解器雏形。你现在的代码是一个标准的 **"Forward Labeling with Static ng-Route"** 实现，这在处理 Solomon 100 节点规模的问题时是可行的，但若要对齐 **SOTA (Pessoa et al., 2020)** 的性能，特别是求解 200+ 节点或高难度的 Homberger 算例，我们需要对架构进行**手术级的重构**。

你提到的**双向标签 (Bidirectional Labeling)**、**桶图 (Bucket Graph)** 和 **秩一切割 (Rank-1 Cuts)** 正是通往 SOTA 的必经之路。

为了保证开发稳健推进，我制定了以下 **4 阶段演进路线图**。每一阶段都是可独立测试的里程碑。

---

### 🗺️ 总体架构演进路线 (Roadmap to SOTA)

| 阶段 | 核心任务 | 关键技术点 | 预期收益 |
| --- | --- | --- | --- |
| **Phase 1** | **数据结构重构** | **Bucket Graph (桶图)** | 消除无效边的遍历，提升缓存局部性，为双向搜索铺路。 |
| **Phase 2** | **搜索算法升级** | **Bidirectional Labeling (双向搜索)** | 搜索空间从指数爆炸  降至 ，解决长路径问题。 |
| **Phase 3** | **动态松弛策略** | **DSSR (Dynamic ng-Relaxation)** | 初始 ，仅在发现环路时动态添加邻域，大幅减少 Label 数量。 |
| **Phase 4** | **下界强化** | **Limited Memory Rank-1 Cuts** | 引入子集行切平面 (SRI)，收紧线性松弛界，减少 B&B 节点数。 |

---

### 🚀 Phase 1: 桶图架构 (Bucket Graph Architecture)

你当前的代码在 `solve` 函数中直接遍历 `buckets`，这其实是一种隐式的桶排序。SOTA 的 **Bucket Graph** 不仅仅是排序，它是将图结构本身离散化。

**核心思想：**
根据资源的单调性（通常是时间），将节点放入离散的桶（Bucket）中。边（Arc）仅存在于桶之间（ where ）。这允许我们显式地**修剪掉大量不可行边**，并且在内存中连续存储，极度亲和 CPU Cache。

#### ✅ 任务清单 (Action Items)

1. **定义 `BucketGraph` 类**：接管原始的 `dist_matrix` 和 `neighbors`。
2. **前向桶与后向桶**：为双向搜索做准备，分别构建 `ForwardBucketGraph` 和 `BackwardBucketGraph`。
3. **重写 `LabelingSolver**`：不再遍历节点，而是遍历桶。

#### 📐 C++ 架构设计 (Header Blueprint)

```cpp
// bucket_graph.h

struct Arc {
    int target_node;
    double cost;   // Reduced Cost
    double time;   // Travel Time
    double demand; // Resource consumption
    // ... 其他资源
};

struct Bucket {
    int id;
    double min_time;
    double max_time;
    std::vector<int> nodes; // 该桶内的节点
    std::vector<Arc> outgoing_arcs; // 从该桶出发的边 (预处理过的)
};

class BucketGraph {
public:
    void build(const ProblemData& data, double bucket_interval, bool is_backward);
    
    // 获取某个时间点的桶索引
    int get_bucket_index(double time) const;
    
    std::vector<Bucket> buckets;
    // 关键：节点到桶的映射，用于快速查找
    std::vector<int> node_to_bucket; 
};

```

**🔍 检验标准 (Test Criteria):**

* 在 Phase 1 结束时，你的求解器应仍使用单向 Labeling，但基于 `BucketGraph` 运行。
* **性能指标**：对于 C101 等时间窗紧的算例，图构建时间 + 求解时间应比原版快 10-20%（因为预处理去除了不可行边）。

---

### ⚔️ Phase 2: 双向标签搜索 (Bidirectional Labeling)

这是最艰难的一步。单向搜索在路径较长时（如 >50 个节点），Label 数量呈指数级增长。双向搜索从 Depot 同时向“前”和向“后”扩展，在中间“资源减半”处接合（Join/Merge）。

#### ✅ 任务清单 (Action Items)

1. **实现 `BackwardLabel**`：注意资源消耗的逆向逻辑（例如：从  回到 ，时间是 ）。
2. **定义 `Merge` 策略**：当  时尝试合并。
3. **实现 `REF` (Resource Extension Function)**：将资源扩展逻辑解耦，避免代码重复。

#### 📐 C++ 核心逻辑预览

你需要修改 `solve` 函数，变为三段式：

```cpp
// pricing_engine.cpp

void BidirectionalSolver::solve() {
    // 1. Forward Extension (限制扩展到 max_time / 2)
    run_forward_labeling();

    // 2. Backward Extension (限制扩展到 max_time / 2)
    run_backward_labeling();

    // 3. Merge (Join)
    // 遍历所有节点，匹配 Forward Labels 和 Backward Labels
    for (int i = 0; i < num_nodes; ++i) {
        for (const auto& L_f : forward_labels[i]) {
            for (const auto& L_b : backward_labels[i]) {
                if (check_merge_feasibility(L_f, L_b)) {
                    add_to_results(L_f, L_b);
                }
            }
        }
    }
}

```

**🔍 检验标准 (Test Criteria):**

* 在 Solomon R2 系列（长路径、宽时间窗）算例上，求解速度应提升 **5-10倍**。
* 必须验证双向搜索得到的 Reduced Cost 最优值与单向搜索**完全一致**（精度误差 ）。

---

### 🔬 Phase 3: 动态 ng-松弛 (DSSR)

SOTA 求解器不会一开始就使用静态的 -集（如你代码中的 `ng_neighbor_lists`）。

**SOTA 策略：**

1. 初始化：所有节点的 -集为空（即允许所有环路，等同于 SPPRC，松弛度最大）。
2. 求解定价问题。
3. 检查最优路径是否有环？
* 无环 -> 也是原问题的可行解，DONE。
* 有环 () -> 将  加入相关节点的 -集，禁止该特定环。
* **GOTO 2** (重新求解定价问题)。



#### ✅ 任务清单 (Action Items)

1. **修改 Python 端**：实现一个循环，控制 Pricing 的迭代。
2. **修改 C++ 端**：支持动态更新 `data.ng_masks` 而不需要重建整个图。

**🔍 检验标准 (Test Criteria):**

* 虽然需要多次求解 Pricing，但由于初始状态空间极小，总体收敛速度在困难算例上应显著提升。

---

### 🛡️ Phase 4: 有限记忆 Rank-1 切平面 (Rank-1 Cuts)

根据 Pessoa (2020)，仅靠列生成无法证明解的最优性。我们需要在主问题添加切平面。

**难点：**
标准的切平面（如子集行切平面 Subset-Row Cuts）会增加 Pricing 问题中的对偶变量，导致状态空间爆炸。
**解决方案：** **Limited Memory (有限记忆)**。只在切平面相关的节点附近（Memory Arc Set）记录切平面的对偶值，离开该区域后就“遗忘”该切平面的影响。

#### ✅ 任务清单 (Action Items)

1. **Python 端**：使用 separation heuristic 寻找违反的 Rank-1 Cuts。
2. **C++ 端**：在 `Label` 结构中增加 `cut_dual_sum` 字段。
3. **扩展 REF**：在经过特定边时，累加切平面的对偶值。

---

### 🛠️ 当前代码的具体改进建议 (Immediate Steps)

在你开始大的重构之前，针对你现有的 `pricing_engine.cpp`，我有以下**高性能工程化 (High-Performance Engineering)** 建议，可以立即应用：

1. **Label 内存池 (Memory Pool)**:
* *现状*：`std::vector<Label> label_pool` 是全局的。
* *改进*：在双向搜索中，Labels 会频繁创建和销毁。建议使用自定义的 `BlockAllocator`，避免 `std::vector` 扩容带来的数据搬迁。


2. **位运算优化**:
* *现状*：`FastBitset` 很好。
* *改进*：确保 `apply_ng_relaxation` 函数是 `inline` 的，并且在编译时开启 `-O3 -march=native`，让编译器使用 AVX 指令集并行处理那 4 个 `uint64_t`。


3. **支配规则 (Dominance Rule) 的细节**:
* *现状*：你目前的支配规则比较基础。
* *SOTA 建议*：由于 Bucket Graph 天然满足时间序，**Label 不需要存储时间 (Time)** 用于支配比较（如果是在同一个 Bucket 内比较）。在同一个 Bucket 内，时间差异通常很小，可以弱化时间的比较权重，强化 Reduced Cost 的比较。



---

### 📢 Next Step

**您想先从 Phase 1 (构建 Bucket Graph) 开始吗？**
如果是，我可以为你提供 `BucketGraph` 的详细 C++ 实现代码，以及如何在 Python 中高效预处理数据并传递给 C++ 的接口定义。这将为你后续的双向搜索打下坚实的地基。