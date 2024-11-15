from copy import copy

from utils.util import reverse_map
from autocomm_v2.gate_util import Gate, GateBlock
from autocomm_v2.gate_util import build_CX_gate, build_H_gate
from autocomm_v2.gate_util import build_M_gate, build_classical_CX_gate, build_classical_CZ_gate

def gate_map_qubits(gate:Gate, mapping):
    new_qubits = [mapping(q) for q in gate.qubits]
    new_gate:Gate = copy(gate)
    new_gate.qubits = new_qubits
    return new_gate

def auto_to_circ(auto_gates, qubit_to_node) -> list[Gate]:
    node_to_qubits = reverse_map(qubit_to_node)
    q_per_node = max([len(v) for k, v in node_to_qubits.items()])

    # the 0th qubit in each section of qubits will be the comm qubit
    qubit_position = {q: node_to_qubits[n].index(q) for q, n in qubit_to_node.items()}
    new_qubit_map = lambda q: qubit_to_node[q]*q_per_node + qubit_position[q] + 1
    # i.e. [0,n] will refer to the 1st n+1 qubits (assigned to node 0). 

    circ = []

    for row in auto_gates:
        if type(row) is Gate:
            circ.append(gate_map_qubits(row, new_qubit_map))
        else:
            assert type(row) is GateBlock
            qubit = row.source
            first_node = row.targets[0]

            if row.is_cat:
                comm_init, comm_final = cat_comm(new_qubit_map(qubit), qubit_to_node[qubit]*q_per_node, first_node*q_per_node)
                circ.extend(comm_init)
            
            curr_node = -1
            for gate in row.gates:
                qubits = gate.qubits
                if len(qubits) == 1:
                    targ_qubit == qubits[0]
                else:
                    targ_qubit = qubits[0] if qubits[1] == qubit else qubits[1]

                if not row.is_cat and curr_node != qubit_to_node[targ_qubit]:
                    circ.extend(tp_comm(new_qubit_map(qubit), qubit_to_node[qubit]*q_per_node, qubit_to_node[targ_qubit]*q_per_node))

                    start_comm = qubit_to_node[qubit]*q_per_node if curr_node == -1 else start_comm
                    curr_node = qubit_to_node[targ_qubit]
                    end_comm = qubit_to_node[targ_qubit]*q_per_node
                
                circ.append(gate_map_qubits(gate, new_qubit_map))
            
            if row.is_cat:
                circ.extend(comm_final)
            else:
                # tp back to the start
                circ.extend(tp_comm(end_comm, start_comm, new_qubit_map(qubit)))
            
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