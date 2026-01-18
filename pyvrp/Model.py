import numpy as np
from ._ProblemData import ProblemData, Client, Depot
from .search.alns import ALNS
from .stop import MaxRuntime

class Model:
    def __init__(self):
        self._clients = []
        self._depots = []
        self._vehicle_types = []
        self._edges = {} # (frm, to) -> (dist, dur)

    def add_client(self, x, y, demand=0, service_duration=0, tw_early=0, tw_late=1_000_000_000):
        client = Client(x, y, demand, service_duration, tw_early, tw_late)
        self._clients.append(client)
        return client

    def add_depot(self, x, y, tw_early=0, tw_late=1_000_000_000):
        depot = Depot(x, y, tw_early, tw_late)
        self._depots.append(depot)
        return depot

    def add_vehicle_type(self, capacity, num_available):
        self._vehicle_types.append({"capacity": capacity, "num_available": num_available})

    def add_edge(self, frm, to, distance, duration):
        self._edges[(frm, to)] = (distance, duration)

    def solve(self, stop, seed=42, display=True):
        # Build ProblemData
        num_locs = len(self._depots) + len(self._clients)
        dist_matrix = np.zeros((num_locs, num_locs), dtype=int)
        duration_matrix = np.zeros((num_locs, num_locs), dtype=int)
        
        locs = self._depots + self._clients
        for i in range(num_locs):
            for j in range(num_locs):
                if (i, j) in self._edges:
                    d, t = self._edges[(i, j)]
                    dist_matrix[i, j] = d
                    duration_matrix[i, j] = t
                else:
                    # Euclidean distance default
                    d = int(np.hypot(locs[i].x - locs[j].x, locs[i].y - locs[j].y))
                    dist_matrix[i, j] = d
                    duration_matrix[i, j] = d # Assume speed 1
        
        data = ProblemData(self._clients, self._depots, dist_matrix, duration_matrix)
        
        alns = ALNS(data, seed=seed)
        result = alns.run(stop)
        return result