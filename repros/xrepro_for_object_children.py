class Graph:
    def childrenOf(self, node):
        return [node + 1, node + 2]


graph = Graph()
total = 0
for node in graph.childrenOf(1):
    total = total + node
print(total)

