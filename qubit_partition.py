import numpy as np
import pymetis
import cirq

from util import dict_append, dict_num_add



def pymetis_partition(circ: cirq.Circuit, num_nodes: int):
    qubits_to_idxs = dict({q: idx for idx, q in enumerate(circ.all_qubits)})
    num_qubits = len(qubits_to_idxs.keys())

    weight_dict = dict() # KEY: {q1, q2}, VALUE: num interactions
    adj_dict = dict() # KEY: q, VALUE: [q_1 ... q_n] interacted qubits

    weights = [] # 2m length array, same as adjs
    adjs = [] # flattened array of adj vertices
    adj_loc = [] # v_i's adj nodes are between adj_loc[i] and adj_loc[i+1] in adj

    for layer in circ:
        for op in layer:
            l = len(op.qubits)
            assert l <= 2, f'Unexpected {l}-qubit gate'
            if l == 1:
                continue

            q1_idx, q2_idx = (qubits_to_idxs[q] for q in op.qubits)
            dict_append(adj_dict, key=q1_idx, append_value=q2_idx)
            dict_append(adj_dict, key=q2_idx, append_value=q1_idx)

            dict_num_add(weight_dict, key={q1_idx, q2_idx}, add_value=1)
    
    for q_idx in range(num_qubits):
        adj_loc.append(len(adjs))
        curr_adjs = adj_dict[q_idx]
        adjs.extend(curr_adjs)

        weights.extend( [weight_dict[{q_idx, adj}] for adj in curr_adjs] )




    ncuts, membership = pymetis.part_graph(num_nodes, xadj=adj_loc, adjncy=adjs, eweights=weights)
    print(f'Number of cuts from pymetis: {ncuts}.\nMembership: {membership}')

    node_to_qubits = dict()
    max_label = max(membership)
    for node in range(max_label + 1):
        q_idxs = np.argwhere(np.array(membership) == node).ravel()
        node_to_qubits[node] = [circ.all_qubits[idx] for idx in q_idxs]
        
    qubit_to_node = dict({circ.all_qubits[idx]: membership[idx] for idx in range(len(membership))})
    return qubit_to_node, node_to_qubits




def OEE():
    pass