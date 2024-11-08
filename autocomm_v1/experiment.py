import random
from numpy import pi
from gate_util import build_H_gate, build_CX_gate, build_RZ_gate, build_toffoli_gate
from autocomm import comm_aggregate, comm_assign, comm_schedule

def run_experiment(circuit_func, num_q=100, qb_per_node=10, refine_iter_cnt=3, verbose=False):
    gate_list, qubit_node_mapping = circuit_func(num_q, qb_per_node)
    
    g_list = comm_aggregate(gate_list, qubit_node_mapping, refine_iter_cnt=refine_iter_cnt)
    assigned_gate_block_list = comm_assign(g_list, qubit_node_mapping)
    
    epr_cnt, all_latency, assigned_gate_block_list1 = comm_schedule(assigned_gate_block_list, qubit_node_mapping, refine_iter_cnt=num_q//qb_per_node)
    
    if verbose:
        print('\n'.join([str(g) for g in assigned_gate_block_list1]))
        print(epr_cnt, all_latency)
    return epr_cnt, all_latency

class CircuitGen:
    def BV(num_qubits, qb_per_node):
        gate_list = []
        for i in range(num_qubits-1):
            gate_list.append(build_CX_gate(0, i+1))
        qubit_node_mapping = [i//qb_per_node for i in range(num_qubits)] # optimal mapping obtained
        return gate_list, qubit_node_mapping

    def QFT(num_qubits, qb_per_node):
        gate_list = []
        for i in range(num_qubits-1):
            gate_list.append(build_H_gate(i))
            for j in range(i+1, num_qubits):
                gate_list.append(build_CX_gate(j,i))
                gate_list.append(build_RZ_gate(i,angle=-pi/4/2**(j-i)))
                gate_list.append(build_CX_gate(j,i))
                gate_list.append(build_RZ_gate(i,angle=pi/4/2**(j-i)))
        qubit_node_mapping = [i//qb_per_node for i in range(num_qubits)] # optimal mapping obtained
        return gate_list, qubit_node_mapping


    def QAOA(num_qubits, qb_per_node, num_terms=200):
        gate_list = []
        for i in range(num_terms):
            qa, qb = random.sample(list(range(num_qubits)), 2)
            gate_list.append(build_CX_gate(qa,qb))
            gate_list.append(build_RZ_gate(qb,angle=0.1))
            gate_list.append(build_CX_gate(qa,qb))
        qubit_node_mapping = [i//qb_per_node for i in range(num_qubits)]
        return gate_list, qubit_node_mapping

    
    def RCA(num_qubits, qb_per_node):
        start_qb = 0
        gate_list = []
        while start_qb < num_qubits-3:
            qa, qb, qc = start_qb, start_qb+1, start_qb+2
            gate_list.append(build_CX_gate(qc,qb))
            gate_list.append(build_CX_gate(qc,qa))
            gate_list += build_toffoli_gate(qa, qb, qc)
            start_qb += 2
        start_qb -= 2
        gate_list.append(build_CX_gate(start_qb,start_qb+1))
        while start_qb > 0:
            qa, qb, qc = start_qb-2,start_qb-1,start_qb
            gate_list += build_toffoli_gate(qa, qb, qc)
            gate_list.append(build_CX_gate(qc,qa))
            gate_list.append(build_CX_gate(qa,qb))
            start_qb -= 2
        qubit_node_mapping = [i//qb_per_node for i in range(num_qubits)] # the optimal one
        return gate_list, qubit_node_mapping
