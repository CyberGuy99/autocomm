from typing import Union
import numpy as np

import cirq
import cirq.circuits
import pymetis

from autocomm_v2.gate_util import Gate
from utils.util import dict_append, dict_num_add, reverse_map


def _pymetis_gate_list_scan(gate_list:Union[list[cirq.Moment], list[Gate]], adj_dict, weight_dict, idx_func):
    for gate in gate_list:
        l = len(gate.qubits)
        assert l <= 2, f'Unexpected {l}-qubit gate'
        if l == 1:
            continue

        q1_idx, q2_idx = idx_func(gate.qubits)
        dict_append(adj_dict, key=q1_idx, append_value=q2_idx)
        dict_append(adj_dict, key=q2_idx, append_value=q1_idx)

        dict_num_add(weight_dict, key=(q1_idx, q2_idx), add_value=1)
        dict_num_add(weight_dict, key=(q2_idx, q1_idx), add_value=1)


def pymetis_partition(num_nodes: int, gate_list: list[Gate] = None, cirq_circ: cirq.Circuit = None):
    
    weight_dict = dict() # KEY: {q1, q2}, VALUE: num interactions
    adj_dict = dict() # KEY: q, VALUE: [q_1 ... q_n] interacted qubits
    
    
    if cirq_circ:
        qubits_to_idxs = dict({q: idx for idx, q in enumerate(cirq_circ.all_qubits)})
        num_qubits = len(qubits_to_idxs.keys())

        def get_qubit_idxs(qubits):
            return (qubits_to_idxs[q] for q in qubits)

        for layer in cirq_circ:
            _pymetis_gate_list_scan(gate_list=layer, adj_dict=adj_dict, weight_dict=weight_dict, idx_func=get_qubit_idxs)

    elif gate_list:
        qubit_indices = set()
        for gate in gate_list:
            for q in gate.qubits:
                qubit_indices.add(q)
        
        num_qubits = max(qubit_indices) + 1
        print('Num Qubits:', num_qubits)

        def get_qubit_idxs(qubits):
            return tuple(q for q in qubits)
        _pymetis_gate_list_scan(gate_list=gate_list, adj_dict=adj_dict, weight_dict=weight_dict, idx_func=get_qubit_idxs)

    else:
        raise RuntimeError("Invalid Input for Pymetis Partition")
    

    adjs = [] # flattened array of adj vertices
    adj_loc = [] # v_i's adj nodes are between adj_loc[i] and adj_loc[i+1] in adj
    weights = [] # 2m length array, same as adjs

    for q_idx in range(num_qubits):
        adj_loc.append(len(adjs))
        curr_adjs = adj_dict[q_idx]
        adjs.extend(curr_adjs)

        weights.extend( [weight_dict[(q_idx, adj)] for adj in curr_adjs] )

    adj_loc.append(len(weights))


    ncuts, membership = pymetis.part_graph(num_nodes, xadj=adj_loc, adjncy=adjs, eweights=weights)
    print(f'Number of cuts from pymetis: {ncuts}.\nMembership: {membership}')

    node_to_qubits = dict()
    max_label = max(membership)
    for node in range(max_label + 1):
        q_idxs = np.argwhere(np.array(membership) == node).ravel()
        if cirq_circ:
            node_to_qubits[node] = [cirq_circ.all_qubits[idx] for idx in q_idxs]
        else:
            node_to_qubits[node] = q_idxs
        
    if cirq_circ:
        qubit_to_node = dict({cirq_circ.all_qubits[idx]: membership[idx] for idx in range(len(membership))})
    else:
        qubit_to_node = reverse_map(node_to_qubits)

    return qubit_to_node, node_to_qubits




def OEE():
    pass


if __name__ == '__main__':
    from autocomm_v2.experiment import CircuitGen
    BV = CircuitGen.BV
    QFT = CircuitGen.QFT
    RCA = CircuitGen.RCA
    N = 10
    b_gl, _ = BV(100, N)
    r_gl, _ = RCA(100, N)
    q_gl, _ = QFT(100, N)
    q_n, n_q = pymetis_partition(N, gate_list=q_gl)
    print(q_n)
    print(n_q)