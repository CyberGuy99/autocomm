import cirq

class Pair:
    # expecting circuit to only have line qubits
    qubit: cirq.LineQubit = None
    node_qubit: cirq.LineQubit = None
    node: int = -1
    qubit_node: int = -1
    is_ctrl: bool = False
    layer_idx: int = -1

    def __init__(self, qubit: cirq.LineQubit, node: int, node_qubit: cirq.LineQubit, qubit_node: int, is_ctrl: bool, layer_idx: int):
        self.qubit = qubit
        self.node_qubit = node_qubit

        self.node = node
        self.qubit_node = qubit_node

        self.is_ctrl = is_ctrl
        self.layer_idx = layer_idx
    
    def is_qubit_control(self):
        return self.is_ctrl
    
    def get_q_node(self):
        return self.qubit_node
    
    def get_ctrl_q(self):
        return self.qubit if self.is_ctrl else self.node_qubit

    def get_targ_q(self):
        return self.node_qubit if self.is_ctrl else self.qubit
    
    def get_op_tuple(self):
        return (self.get_ctrl_q(), self.get_targ_q())

class Block:
    pairs: list[Pair] = [] # collection of 2-qubit ops and their metadat
    def __init__(self, pairs):
        self.pairs = pairs

    def start_pair_idx(self):
        return self.pairs[0].layer_idx

    def end_pair_idx(self):
        return self.pairs[-1].layer_idx