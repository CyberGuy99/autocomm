import cirq
from utils.util import dict_append

sync_gates = {cirq.H, cirq.Rx, cirq.Ry, cirq.CNOT, 'H', 'RX', 'RY', 'CNOT'}

def _read_gate_lifetime(gates, lifetime_dict, get_qubit_idx, end_measure=False):
    last_gate = dict()
    get_gate_type = lambda g: g.gate if type(gate) is cirq.Operation else g['type']

    for gate in gates:
        curr_id = get_qubit_idx(gate)
        last_gate[curr_id] = gate
        # increment latest lifetime for target qubit
        lifetime_dict[curr_id][-1] += 1

        gate_type = get_gate_type(gate)
        if gate_type in sync_gates:
            # start a new lifetime count for target qubit (exclude the current op from length)
            dict_append(d=lifetime_dict, key=curr_id, append_value=0)
    
    for q_id, gate in last_gate.items():
        # check if last segment is open or closed
        # if the qubit is the target of a sync gate, then it is closed
        if get_gate_type(gate) in sync_gates:
            # should have a 0 at the end
            assert lifetime_dict[q_id][-1] == 0
            lifetime_dict[q_id] = lifetime_dict[q_id][:-1]
            continue

        if end_measure:
            lifetime_dict[q_id][-1] += 1 # lifetime ends at the implied measure gate
        else:
            lifetime_dict[q_id] = lifetime_dict[q_id][:-1] # exclude the last open segment

# lifetime for a block is defined as the number of gates 
# (including the sync gates, which mark the start and end of the block)
# if no sync gates remaining, continue incrementing until the end of the circuit
def get_lifetimes(input_replica = None, input_cirq: cirq.Circuit = None):
    if not input_replica and not input_cirq:
        print('Empty Input.')
        return None, None
    
    if input_cirq:
        qubit_idxs = dict( {qubit: id for id, qubit in enumerate(input_cirq.all_qubits)} )
        num_qubits = len(qubit_idxs)
        get_target_idx = lambda g: qubit_idxs[g.qubits[-1]]
    else:
        qubit_idxs = set()
        for gate in input_replica:
            for q in gate['qubits']:
                qubit_idxs.add(q)
        
        num_qubits = max(qubit_idxs) + 1
        get_target_idx = lambda g: g['qubits'][-1]


    lifetime_dict = dict( {id: [0] for id in range(num_qubits)} )

    if input_cirq:
        [_read_gate_lifetime(layer, lifetime_dict, get_target_idx) for layer in input_cirq]
    else:
        _read_gate_lifetime(input_replica, lifetime_dict, get_target_idx)

                    

    return lifetime_dict, qubit_idxs
