'''g_list: a list of gates
'''
from numpy import exp, pi, isclose
from copy import deepcopy

def gate_list_to_layer(g_list):
    num_q_slot = max([max(g[1]) for g in g_list]) + 1
    q_slot = [0 for i in range(num_q_slot)]
    layer_list = []
    for g in g_list:
        g_layer_id = max([q_slot[qb] for qb in g[1]])
        if g_layer_id >= len(layer_list):
            layer_list.append([])
        layer_list[g_layer_id].append(g)
        for qb in g[1]:
            q_slot[qb] = g_layer_id + 1
    return layer_list


class Gate:
    type: str = None
    qubits: list[int] = []
    params: list[float] = []
    global_phase: int = 1

    def __init__(self, _type, qubits, params=[], global_phase=1):
        self.type = _type
        self.qubits = qubits
        self.params = params
        self.global_phase = global_phase
    
    def from_list(gate_list:list):
        return Gate(*gate_list)

    def transform(self, type:str=None, qubits:list[int]=None, params:list[float]=None, global_phase:int=None):
        type = self.type if type is None else type
        qubits = self.qubits if qubits is None else qubits
        params = self.params if params is None else params
        global_phase = self.global_phase if global_phase is None else global_phase
        return Gate(_type=type, qubits=qubits, params=params, global_phase=global_phase)
    

    def is_comm(self, qubit_node_mapping):
        if len(self.qubits) == 1:
            return False
        nodes = [qubit_node_mapping[q] for q in self.qubits]
        return not all([n == nodes[0] for n in nodes])

    
    def __copy__(self):
        return Gate(_type=self.type, qubits=self.qubits.copy(), \
                     params=self.params.copy(), global_phase=self.global_phase) 

    def __str__(self):
        return f'{self.type}({self.qubits},, {self.params}) * {self.global_phase}'

    def __equals__(self, other): 
        if type(other) != Gate:
            return False
        return self.__str__() == str(other)

def sanity_check_count(l, qubit_node_mapping):
    blocks = [g for g in l if type(g) is GateBlock]
    block_target_cnts = [b.check_target_counts(qubit_node_mapping) for b in blocks]
    assert all(block_target_cnts), f'num targets mismatch num gates: {block_target_cnts}'
    return blocks, block_target_cnts

def get_target(qubits, source, qubit_node_mapping):
    if len(qubits) == 1:
        return qubit_node_mapping[qubits]
    assert len(qubits) == 2
    target_idx = int(source == qubits[0])
    return qubit_node_mapping[qubits[target_idx]]
    

def add_unique_only(l:list, to_add, verbose=False):
    if verbose:
        print(to_add)
        print(l)
    if type(to_add) is list:
        for item in to_add:
            if item not in l:
                l.append(item)
        if verbose:
            print(l)
            print('done')
    elif to_add not in l:
        l.append(to_add)

class GateBlock:
    is_cat: bool = False
    source: int = -1 # source qubit
    targets: list[int] = [] # target nodes
    targets_no_dups: list[int] = []
    gates: list[Gate] = []

    def __init__(self, source:int = -1, targets:list[int] = [], gates:list[Gate] = [], is_cat:bool = False):
        self.source = source
        self.targets = targets
        self.targets_no_dups = []
        add_unique_only(self.targets_no_dups, targets)
        self.is_cat = is_cat
        self.gates = gates
    
    def empty_source_target(self):
        num_true = int(self.source == -1) + int(len(self.targets) == 0)
        assert num_true != 1
        return num_true == 2
    

    def check_target_counts(self, qubit_node_mapping):
        if self.empty_source_target():
            return True
        return len(self.targets) == len(self.get_comm_gates(qubit_node_mapping))

    def set_source_target(self, source:int, target:int, qubit_node_mapping=None):
        self.source = source
        if qubit_node_mapping:
            self.targets = [target]*len(self.get_comm_gates(qubit_node_mapping))
        else:
            self.targets = [target]*len(self.gates)
        self.targets_no_dups = [target]
    
    def get_source_target(self, qubit_node_mapping=None):
        if qubit_node_mapping:
            assert self.check_target_counts(qubit_node_mapping), \
                f'{self.__str__()}\n num targets ({len(self.targets)}) != num gates ({len(self.get_comm_gates(qubit_node_mapping))})' 

        assert all([t == self.targets[0] for t in self.targets]), \
              'Multiple targets for GateBlock'

        return self.source, self.targets[0]

    '''
    def add_gate(self, gate:Gate, target:int=-1, qubit_node_mapping=None):
        self.gates.append(gate)
        if qubit_node_mapping and not self.check_target_counts(qubit_node_mapping):
            if target >= 0:
                self.targets.append(target)
            else:
                # assumes new gate has same node as previous
                self.targets.append(self.targets[-1]) # copy previous target

    def add_targets(self, targets: list[int]):
        self.targets.extend(targets)
        add_unique_only(self.targets_no_dups, targets)
    '''
    
    def get_comm_gates(self, qubit_node_mapping):
        return [g for g in self.gates if g.is_comm(qubit_node_mapping)]

    def __str__(self):
        gate_str = '\n'.join([str(gate) for gate in self.gates])
        return f'({self.source}, {self.targets}, {self.targets_no_dups}) -- {self.is_cat}::\n' + gate_str  + '\n-----\n'

    def __deepcopy__(self, memo):
        return GateBlock(source=self.source, targets=self.targets.copy(), \
                         gates=deepcopy(self.gates), is_cat=self.is_cat)


def gateblock_list_str(l, filter_lambda=None):
    if not filter_lambda:
        filter_lambda = lambda x: True
    return '\n'.join([str(b) for b in l if filter_lambda(b)])


'''
def g.type: return g[0]
def gate_qubits(g): return [qb for qb in g[1]]
def gate_params(g): 
    if len(g) > 2:
        return [param for param in g[2]]
    else:
        return []

def is_equal_gate(g0, g1): return g0 == g1

def build_gate(name, qubits, params=[], global_phase=1):
    return [name, qubits, params, global_phase]
'''

def build_gate(name, qubits, params=[], global_phase=1):
    return Gate(_type=name, qubits=qubits, params=params, global_phase=global_phase)

def build_T_gate(qb):
    return build_RZ_gate(qb, [1j*pi/4], global_phase=exp(-1j*pi/8))

def build_S_gate(qb):
    return build_RZ_gate(qb, [1j*pi/2], global_phase=exp(-1j*pi/4))

def build_Tdg_gate(qb):
    return build_RZ_gate(qb, [-1j*pi/4], global_phase=exp(1j*pi/8))

def build_Sdg_gate(qb):
    return build_RZ_gate(qb, [-1j*pi/2], global_phase=exp(1j*pi/4))

def build_RZ_gate(qb, angle, global_phase=1):
    return build_gate("RZ", [qb], [angle], global_phase=global_phase)

def build_RX_gate(qb, angle, global_phase=1):
    return build_gate("RX", [qb], [angle], global_phase=global_phase)

def build_H_gate(qb):
    return build_gate("H", [qb])

def build_CX_gate(ctrl, target):
    return build_gate("CX", [ctrl, target])

def build_CZ_gate(ctrl, target):
    return build_gate("CZ", [ctrl, target])

def build_CRZ_gate(ctrl, target, angle):
    return build_gate("CRZ", [ctrl, target], [angle])

def build_toffoli_gate(qa, qb, qc):
    gate_list = []
    gate_list.append(build_H_gate(qc))
    gate_list.append(build_CX_gate(qb,qc))
    gate_list.append(build_Tdg_gate(qc))
    gate_list.append(build_CX_gate(qa,qc))
    gate_list.append(build_T_gate(qc))
    gate_list.append(build_CX_gate(qb,qc))
    gate_list.append(build_Tdg_gate(qc))
    gate_list.append(build_CX_gate(qa,qc))
    gate_list.append(build_T_gate(qb))
    gate_list.append(build_T_gate(qc))
    gate_list.append(build_H_gate(qc))
    gate_list.append(build_CX_gate(qa,qb))
    gate_list.append(build_T_gate(qa))
    gate_list.append(build_Tdg_gate(qb))
    gate_list.append(build_CX_gate(qa,qb))
    return gate_list

def crz_merge(g_list):
    layer_list = [[g] for g in g_list] # gate_list_to_layer(g_list)
    layer_qb_dict_list = []
    layer_qb_dict_list_control = []
    layer_qb_dict_list_target = []
    layer_gate_deleted = []
    for layer in layer_list:
        qb_dict = {}
        qb_dict_control = {}
        qb_dict_target = {}
        g_del_flag = []
        for gidx, g in enumerate(layer):
            qubits = g.qubits
            qb_dict[tuple(qubits)] = [gidx, g]
            if g.type == "CX":
                qb_dict_control[qubits[0]] = g
                qb_dict_target[qubits[1]] = g
            elif len(qubits) == 1:
                qb_dict_target[qubits[0]] = g
            g_del_flag.append(0)
        layer_qb_dict_list.append(qb_dict)
        layer_qb_dict_list_control.append(qb_dict_control)
        layer_qb_dict_list_target.append(qb_dict_target)
        layer_gate_deleted.append(g_del_flag)

    new_gate_list = []
    for lidx, layer in enumerate(layer_list):
        for gidx0, g0 in enumerate(layer):
            if layer_gate_deleted[lidx][gidx0] == 0:
                if g0.type == "CX" and (lidx+2) < len(layer_list):
                    qb = g0.qubits
                    next_lqd = layer_qb_dict_list[lidx+1]
                    next_next_lqd = layer_qb_dict_list[lidx+2]
                    _merge_flag = False
                    if tuple([qb[1]]) in next_lqd and tuple(qb) in next_next_lqd:
                        gidx1, g1 = next_lqd[tuple([qb[1]])]
                        gidx2, g2 = next_next_lqd[tuple(qb)]
                        if g1.type == "RZ" and g2.type == "CX":
                            if qb[0] in layer_qb_dict_list_control[lidx+1]:
                                _merge_flag = True
                            elif qb[0] not in layer_qb_dict_list_target[lidx+1]:
                                _merge_flag = True
                            else:
                                g3 = layer_qb_dict_list_target[lidx+1][qb[0]]
                                if g3.type == "RZ":
                                    _merge_flag = True
                    if _merge_flag:
                        layer_gate_deleted[lidx+1][gidx1] = 1
                        layer_gate_deleted[lidx+2][gidx2] = 1
                        new_gate_list.append(build_gate("CRZ", qb, [-2*param for param in g1.params]))
                        new_gate_list.append(build_gate("RZ", qb[1:], [param for param in g1.params]))
                    else:
                        new_gate_list.append(g0)
                else:
                    new_gate_list.append(g0)
            else:
                pass
    gate_del_flag = [0 for i in range(len(new_gate_list))]
    r_gate_list = []
    for gidx, g in enumerate(new_gate_list):
        if gate_del_flag[gidx] == 0:
            if gidx == len(new_gate_list) - 1:
                break
            g1 = new_gate_list[gidx+1]
            if g.type == "RZ":
                if g1.type == g.type and g.qubits == g1.qubits and isclose(g.params[0],-g1.params[0]):
                    gate_del_flag[gidx] = 1
                    gate_del_flag[gidx+1] = 1
                else:
                    r_gate_list.append(g)
            else:
                r_gate_list.append(g)
    return r_gate_list

def pattern_merged_circ(g_list, pattern_func_list=[crz_merge]):
    for pattern_func in pattern_func_list:
        g_list = pattern_func(g_list)
    return g_list

def remove_repeated_gates(gate_list):
    n_gate = len(gate_list)
    gate_del_flag = [0 for i in range(n_gate)]
    new_gate_list = []
    for gidx0, g0 in enumerate(gate_list):
        if gate_del_flag[gidx0] == 0:
            for gidx1 in range(gidx0+1, n_gate):
                g1 = gate_list[gidx1]
                if g0.equals(g1):
                    gate_del_flag[gidx0] = 1
                    gate_del_flag[gidx1] = 1
                    break
            if gate_del_flag[gidx0] == 0:
                new_gate_list.append(g0)
    return new_gate_list

if __name__ == "__main__":
    g_list = [build_gate("RZ", [0], [0.1]),build_gate("CX", [1,2]),build_gate("RZ", [2], [0.1]),build_gate("CX", [1,2]), \
              build_gate("CX", [2,3]),build_gate("RZ", [3], [0.1]),build_gate("RZ", [2], [0.1]),build_gate("CX", [2,3]), build_gate("RZ", [0], [0.1]) \
            ]
    print(crz_merge(g_list))
                        
    
