from autocomm_v1.gate_util import build_CX_gate, build_H_gate
from autocomm_v1.gate_util import build_M_gate, build_classical_CX_gate, build_classical_CZ_gate
from utils.util import reverse_map

def gate_map_qubits(gate, mapping):
    new_qubits = [mapping(q) for q in gate[1]]
    new_gate = gate.copy()
    new_gate[1] = new_qubits
    return new_gate

def auto_to_circ(auto_gates, qubit_to_node):
    node_to_qubits = reverse_map(qubit_to_node)
    q_per_node = max([len(v) for k, v in node_to_qubits.items()])

    # the 0th qubit in each section of qubits will be the comm qubit
    qubit_position = {q: node_to_qubits[n].index(q) for q, n in qubit_to_node.items()}
    new_qubit_map = lambda q: qubit_to_node[q]*q_per_node + qubit_position[q] + 1
    # i.e. [0,n] will refer to the 1st n+1 qubits (assigned to node 0). 

    circ = []

    for row in auto_gates:
        key = row[0]
        if type(key) is str:
            circ.append(gate_map_qubits(row, new_qubit_map))
        else:
            do_tp = bool(key[1])
            qubit = key[0][0]
            nodes = key[0][1:]
            gates = row[1]

            if not do_tp:
                comm_init, comm_final = cat_comm(new_qubit_map(qubit), qubit_to_node[qubit]*q_per_node, nodes[0]*q_per_node)
                circ.extend(comm_init)
            
            curr_node = -1
            for gate in gates:
                qubits = gate[1]
                if len(qubits) == 1:
                    targ_qubit == qubits[0]
                else:
                    targ_qubit = qubits[0] if qubits[1] == qubit else qubits[1]

                if do_tp and curr_node != qubit_to_node[targ_qubit]:
                    circ.extend(tp_comm(new_qubit_map(qubit), qubit_to_node[qubit]*q_per_node, qubit_to_node[targ_qubit]*q_per_node))

                    start_comm = qubit_to_node[qubit]*q_per_node if curr_node == -1 else start_comm
                    curr_node = qubit_to_node[targ_qubit]
                    end_comm = qubit_to_node[targ_qubit]*q_per_node
                
                circ.append(gate_map_qubits(gate, new_qubit_map))
            
            if do_tp:
                # tp back to the start
                circ.extend(tp_comm(end_comm, start_comm, new_qubit_map(qubit)))
            else:
                circ.extend(comm_final)
            
    return circ

            

def tp_comm(q, source_comm, targ_comm):
    gates = []
    gates.append(build_CX_gate(q, source_comm))
    gates.append(build_H_gate(q))

    gates.append(build_M_gate(source_comm))
    gates.append(build_classical_CX_gate(source_comm, targ_comm))

    gates.append(build_M_gate(q))
    gates.append(build_classical_CZ_gate(source_comm, targ_comm))
    return gates

def cat_comm(q, source_comm, targ_comm):
    init_gates = []
    init_gates.append(build_CX_gate(q, source_comm))
    init_gates.append(build_M_gate(source_comm))
    init_gates.append(build_classical_CX_gate(source_comm, targ_comm))

    final_gates = []
    final_gates.append(build_H_gate(targ_comm))
    final_gates.append(build_M_gate(targ_comm))
    final_gates.append(build_classical_CZ_gate(targ_comm, q))

    return init_gates, final_gates