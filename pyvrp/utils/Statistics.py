class Statistics:
    def __init__(self):
        self.history = []

    def collect(self, solution):
        self.history.append(solution.cost())