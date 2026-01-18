# tests/test_read.py
from pyvrp.read import read
import os

def test_read_solomon():
    # 假设你有一个 data 文件夹，里面放了 C101.txt
    # 如果没有，可以先手动创建一个极简的文件进行测试
    file_path = "data/C101.txt"
    
    if not os.path.exists(file_path):
        print(f"跳过测试：未找到文件 {file_path}")
        return

    data = read(file_path)
    
    print(f"成功加载算例: {file_path}")
    print(f"客户数量: {data.num_clients}")
    print(f"车辆容量: {data._vehicle_capacity}")
    print(f"仓库坐标: ({data._depots[0].x}, {data._depots[0].y})")
    
    # 验证第一个客户的数据
    c1 = data._clients[0]
    print(f"1号客户需求: {data.demand(1)}")
    
    assert data.num_clients > 0
    print("✅ Read 模块测试通过！")

if __name__ == "__main__":
    test_read_solomon()