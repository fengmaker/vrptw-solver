class Result:
    def __init__(self, best_solution, runtime):
        self._best_solution = best_solution
        self._runtime = runtime

    @property
    def best(self):
        return self._best_solution
        
    @property
    def runtime(self):
        return self._runtime
        
    def __str__(self):
        return f"Result(cost={self.best.cost()}, runtime={self.runtime:.2f}s)"