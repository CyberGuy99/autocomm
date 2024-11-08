import cirq
from utils.util import dict_append

sync_gates = {cirq.H, cirq.Rx, cirq.Ry, cirq.CNOT}

# lifetime for a block is defined as the number of gates 
# (including the sync gates, which mark the start and end of the block)
# if no sync gates remaining, continue incrementing until the end of the circuit
def get_lifetimes(input_circ: cirq.Circuit):
    qubit_to_id = dict( {qubit: id for id, qubit in enumerate(input_circ.all_qubits)} )
    num_qubits = len(qubit_to_id)
    lifetime_dict = dict( {id: [0] for id in range(num_qubits)} )

    for layer in input_circ:
        for op in layer:
            curr_id = qubit_to_id[op.qubits[0]]
            if len(op.qubits == 2):
                curr_id = qubit_to_id[op.qubits[1]]

            # increment latest lifetime for target qubit
            lifetime_dict[curr_id][-1] += 1

            if op.gate in sync_gates:
                
                # start a new lifetime count for target qubit (include the current op in length)
                dict_append(d=lifetime_dict, key=curr_id, append_value=1)
                    

    return lifetime_dict, qubit_to_id
