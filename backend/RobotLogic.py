from collections import deque



class RobotLogic:
    def __init__(self, robot_id, start_x, start_y, grid):
        # current robot position
        self.x = start_x
        self.y = start_y

        # reference to the shared grid map
        self.grid = grid

        # unique robot identifier
        self.robot_id = robot_id

    def _cell(self, x, y):
        # return cell content at (x, y)
        row = self.grid[y]
        return row[x] if isinstance(row, str) else row[x]

    def _is_free(self, x, y):
        # check grid bounds
        if not (0 <= y < len(self.grid) and 0 <= x < len(self.grid[0])):
            return False

        # cell is free if it is not a wall
        return self._cell(x, y) != "#"

    def _neighbors(self, x, y):
        # generate valid neighboring cells
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if self._is_free(nx, ny):
                yield nx, ny

    def find_path_bfs(self, sx, sy, tx, ty):
        # Breadth-First Search to find shortest path on grid

        # already at target
        if (sx, sy) == (tx, ty):
            return []

        # BFS queue and predecessor map
        q = deque([(sx, sy)])
        prev = {(sx, sy): None}

        # explore grid
        while q:
            x, y = q.popleft()

            # target reached
            if (x, y) == (tx, ty):
                break

            # visit neighbors
            for nx, ny in self._neighbors(x, y):
                if (nx, ny) not in prev:
                    prev[(nx, ny)] = (x, y)
                    q.append((nx, ny))

        # no path found
        if (tx, ty) not in prev:
            return None

        # reconstruct path (excluding start, including target)
        path = []
        cur = (tx, ty)
        while cur != (sx, sy):
            path.append(cur)
            cur = prev[cur]

        path.reverse()
        return path

    def calculate_path(self, task):
        # extract task target position
        tx = task.location.x
        ty = task.location.y

        # plan path to target
        path = self.find_path_bfs(self.x, self.y, tx, ty)

        # abort task if no path exists
        if path is None:
            print(f"[RobotLogic] No path to ({tx},{ty}) found, aborting task")
            return self.x, self.y

        return path