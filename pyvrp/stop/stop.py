class StopCriterion:
    def __call__(self, best_cost):
        raise NotImplementedError

class MaxRuntime(StopCriterion):
    def __init__(self, max_runtime):
        self.max_runtime = max_runtime
        
    def __call__(self, best_cost):
        # Logic to check runtime against start time
        return False

class MaxIterations(StopCriterion):
    def __init__(self, max_iterations):
        self.max_iterations = max_iterations
        self.current_iteration = 0
        
    def __call__(self, best_cost):
        self.current_iteration += 1
        return self.current_iteration >= self.max_iterations