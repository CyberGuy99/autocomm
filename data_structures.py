import cirq

class Pair:
    # expecting circuit to only have line qubits
    qubit: cirq.LineQubit = None
    node_qubit: cirq.LineQubit = None
    node: int = None
    is_ctrl: bool = False
    layer_idx: int = -1

    def __init__(self, qubit: cirq.LineQubit, node: int, node_qubit: cirq.LineQubit, is_ctrl: bool, layer_idx: int):
        self.qubit = qubit
        self.node_qubit = node_qubit
        self.node = node
        self.is_ctrl = is_ctrl
        self.layer_idx = layer_idx
    
    def is_qubit_control(self):
        return self.is_ctrl
    
    def get_qubit_node(self):
        global node_map
        return node_map[self.qubit]

class Block:
    pairs: list[Pair] = [] # collection of 2-qubit ops and their metadat
    def __init__(self, pairs):
        self.pairs = pairs

    def start_layer_idx(self):
        return self.layers[0].layer_idx

    def end_layer_idx(self):
        return self.layers[-1].layer_idx