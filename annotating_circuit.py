from os.path import join
from pickle import load, dump
import simpy

from autocomm_v2.gate_util import Gate
from autocomm_v2.autocomm import full_autocomm
from autocomm_v2.final_circuit import auto_to_circ
from replica import get_lifetimes
from utils.util import dict_num_add

# Define delay times
SINGLE_QUBIT_GATE_DELAY = 1
TWO_QUBIT_GATE_DELAY = 10
ENTANGLEMENT_DELAY = 100

class QuantumGate:
    def __init__(self, gate_type, qubits, qpus_involved, circuit, initiating_qpu):
        self.gate_type = gate_type
        self.qubits = qubits
        self.qpus_involved = qpus_involved  # List of involved QPUs
        self.circuit = circuit
        self.initiating_qpu = initiating_qpu  # QPU that initiates the execution of the gate

    def is_remote(self):
        return len(self.qpus_involved) > 1

class Circuit:
    def __init__(self, env, circuit_id, gates, qpus, scheduler):
        self.env = env
        self.circuit_id = circuit_id
        self.gates = gates
        self.qpus = qpus
        self.scheduler = scheduler
        self.completion_event = env.event()
        self.remaining_gates = len(gates)
        self.logical_to_physical = {}  # Mapping from logical qubits to physical qubits
        self.action = env.process(self.run())

    def run(self):
        # Output the logical-to-physical qubit mapping
        print(f"Time {self.env.now}: Circuit {self.circuit_id}'s logical-to-physical qubit mapping:")
        for logical_qubit, (qpu_id, physical_qubit) in self.logical_to_physical.items():
            print(f"  Logical qubit {logical_qubit} -> QPU {qpu_id}, physical qubit {physical_qubit}")
        # Map gates to the corresponding QPU
        physical_qubits_involved = set()
        remote_qubit_demand = dict({qpu_id: dict() for qpu_id in self.qpus.keys()})
        for gate in self.gates:
            qpus_involved = set()
            for logical_qubit in gate['qubits']:
                qpu_id, physical_qubit = self.logical_to_physical[logical_qubit]
                qpus_involved.add(qpu_id)
                physical_qubits_involved.add((self.qpus[qpu_id], physical_qubit))

            # TODO should we sort this?
            qpus_involved = list(qpus_involved)
            initiating_qpu_id = qpus_involved[0]
            initiating_qpu = self.qpus[initiating_qpu_id]
            gate_obj = QuantumGate(gate['type'], gate['qubits'], qpus_involved, self, initiating_qpu)
            # Only place the gate in the initiating QPU's queue
            initiating_qpu.gate_queue.put(gate_obj)

            # Measuring demand for Replica Allocation
            if gate_obj.is_remote():
                for i, qpu_id in enumerate(qpus_involved):
                    other_phys_qubit = self.logical_to_physical[gate['qubits'][i-1]]
                    dict_num_add(remote_qubit_demand[qpu_id], other_phys_qubit, 1) 
        
        # Mark replica qubits
        print(physical_qubits_involved)
        for qpu, physical_qubit in physical_qubits_involved:
            qpu.replica_qubits.remove(physical_qubit)
        # Allocate Replicas
        for qpu_id, qpu in self.qpus.items():
            qpu.allocate_replicas(remote_qubit_demand[qpu_id])
        # Wait for the circuit to complete execution
        yield self.completion_event
        self.stats()
        for qpu in self.qpus.values():
            qpu.reset()
        # Release physical qubit resources
        self.scheduler.release_qubits(self)
        self.scheduler.active_circuits.remove(self)
        # Activate scheduler to execute the next circuit
        yield self.env.process(self.scheduler.run())
        print(f"Time {self.env.now}: Scheduler detected that circuit {self.circuit_id} has completed, activating the next circuit")

    # Display simulation stats
    def stats(self):
        qpu_stats = []
        print('============================================')
        print(f'Circuit {self.circuit_id} Simulation Stats:::')
        print(f'End Time: {self.env.now}, Num Entangling Operations: {sum(qpu.num_circ_entangled for qpu in self.qpus.values())}')
        for qpu in self.qpus.values():
            qpu_stats.append(qpu.stats())
        print('============================================')
        return qpu_stats
 

    def gate_done(self):
        self.remaining_gates -= 1
        if self.remaining_gates == 0:
            self.completion_event.succeed()

class QPU:
    def __init__(self, env, qpu_id, num_computing_qubits, num_communication_qubits, use_replica=True):
        self.env = env
        self.qpu_id = qpu_id
        self.num_computing_qubits = num_computing_qubits
        self.num_communication_qubits = num_communication_qubits
        self.gate_queue = simpy.Store(env)
        # Initialize computing qubits, each represented by a resource
        self.qubits = {i: simpy.Resource(env, capacity=1) for i in range(num_computing_qubits)}
       # Initialize communication qubits, each represented by a resource
        self.communication_qubits = {i: simpy.Resource(env, capacity=1) for i in range(num_communication_qubits)}
        # Allocation status of physical qubits
        self.qubit_allocation = {} # TODO UNUSED
        self.action = env.process(self.run())

        # Replica variables
        self.use_replica = use_replica
        self.replica_qubits = set(range(num_computing_qubits)) # indices that represent unused physical computing qubits
        self.replica_qubit_states = dict() # KEY: computing_qubit_id , VALUE: physical qubit (qpu_id, computing_qubit_id)
        self.outside_qubit_replica = dict() # KEY: physical qubit (qpu_id, computing_qubit_id), VALUE: computing_qubit_id
 
        # Statistics variables
        self.num_total_entangled = 0
        self.num_circ_entangled = 0
        self.start_time = self.env.now
        self.replica_usage = dict()

    def reset(self):
        self.num_circ_entangled = 0
        self.replica_qubits = set(range(self.num_computing_qubits))
        self.replica_qubit_states = dict()
        self.outside_qubit_replica = dict()
        self.start_time = self.env.now
        self.replica_usage = dict()
    
    def stats(self):
        header = f'{self.qpu_id} Stats::'
        total_stats = f'Total:: Duration: {self.env.now}, Entangled: {self.num_total_entangled}'
        circ_stats = f'Circ:: Duration: {self.env.now - self.start_time}, Entangled: {self.num_circ_entangled}'
        print(self.replica_qubits)
        replica_stats = f'Num Replica: {len(self.replica_qubits)}'
        for r_qubit, usage in self.replica_usage.items():
            replica_stats += f'\n\t{r_qubit} : {usage}'

        print(header + '\n' + total_stats + '\n' + circ_stats + '\n' + replica_stats)
        return total_stats, circ_stats, replica_stats
    
    def allocate_replicas(self, physical_qubit_demand, strategy=None):
        if len(self.replica_qubit_states) == 0:
            return
        
        if strategy:
            sorted_demanded_qubits = sorted(physical_qubit_demand.keys(), key = strategy)
        else:
            sorted_demanded_qubits = sorted(physical_qubit_demand.keys(), key = lambda k: physical_qubit_demand[k], reverse=True)
        
        for i, replica in enumerate(self.replica_qubits):
            self.replica_qubit_states[replica] = sorted_demanded_qubits[i]
            self.outside_qubit_replica[sorted_demanded_qubits[i]] = replica

    def run(self):
        while True:
            # TODO why yield? can a gate be inside more than one QPU's queue?
            gate = yield self.gate_queue.get()
            # Only process gates initiated by this QPU
            if self != gate.initiating_qpu:
                continue
            # Start a new process to execute the gate without waiting for its completion
            self.env.process(self.execute_gate(gate))

    def execute_gate(self, gate):
        if len(gate.qubits) == 1:
            # Single-qubit gate
            yield self.env.process(self.execute_single_qubit_gate(gate))
        elif len(gate.qubits) == 2:
            if gate.is_remote():
                # Remote two-qubit gate
                yield self.env.process(self.execute_remote_gate(gate))
            else:
                # Local two-qubit gate
                yield self.env.process(self.execute_local_two_qubit_gate(gate))
        # Notify the circuit that the gate is done
        gate.circuit.gate_done()

    def execute_single_qubit_gate(self, gate):
        logical_qubit = gate.qubits[0]
        circuit = gate.circuit
        qpu_id, physical_qubit = circuit.logical_to_physical[logical_qubit]
        assert qpu_id == self.qpu_id, "QPU for the single-qubit gate does not match the QPU where the logical qubit is located"
        with self.qubits[physical_qubit].request() as req:
            yield req
            print(f"Time {self.env.now}: QPU {self.qpu_id} starts executing single-qubit gate {gate.gate_type} on logical qubit {logical_qubit} (physical qubit {physical_qubit}) in circuit {circuit.circuit_id}")
            yield self.env.timeout(SINGLE_QUBIT_GATE_DELAY)
            print(f"Time {self.env.now}: QPU {self.qpu_id} completes single-qubit gate {gate.gate_type} (circuit {circuit.circuit_id}, logical qubit {logical_qubit})")

    def execute_local_two_qubit_gate(self, gate):
        circuit = gate.circuit
        logical_qubit1, logical_qubit2 = gate.qubits
        qpu_id1, physical_qubit1 = circuit.logical_to_physical[logical_qubit1]
        qpu_id2, physical_qubit2 = circuit.logical_to_physical[logical_qubit2]
        assert qpu_id1 == self.qpu_id == qpu_id2, "QPU for the local two-qubit gate does not match the QPU where the logical qubits are located"
        with self.qubits[physical_qubit1].request() as req1, self.qubits[physical_qubit2].request() as req2:
            yield req1 & req2
            print(f"Time {self.env.now}: QPU {self.qpu_id} starts executing local two-qubit gate {gate.gate_type} on logical qubits {logical_qubit1}, {logical_qubit2} in circuit {circuit.circuit_id}")
            yield self.env.timeout(TWO_QUBIT_GATE_DELAY)
            print(f"Time {self.env.now}: QPU {self.qpu_id} completes local two-qubit gate {gate.gate_type} (circuit {circuit.circuit_id})")

    def execute_remote_gate(self, gate):
        circuit = gate.circuit
        # Get local logical qubits and corresponding physical qubits
        local_logical_qubits = [q for q in gate.qubits if circuit.logical_to_physical[q][0] == self.qpu_id]
        local_physical_qubits = [circuit.logical_to_physical[q][1] for q in local_logical_qubits]
        # Request resources for local physical qubits
        data_qubit_requests = [self.qubits[qubit_id].request() for qubit_id in local_physical_qubits]
        yield simpy.events.AllOf(self.env, data_qubit_requests)
        # Try Replica
        remote_physical_qubits = [circuit.logical_to_physical[q] for q in gate.qubits if circuit.logical_to_physical[q][0] != self.qpu_id]

        if self.use_replica:
            used_replica_qubits = [self.outside_qubit_replica[p_qubit_id] for p_qubit_id in remote_physical_qubits if p_qubit_id in self.outside_qubit_replica]
            replica_qubit_requests = []
            for r_qubit_id in used_replica_qubits:
                dict_num_add(self.replica_usage, r_qubit_id, 1)
                replica_qubit_requests.append(self.qubits[r_qubit_id].request())
            yield simpy.events.AllOf(self.env, replica_qubit_requests)
            remaining_remote_qubits = [p_qubit for p_qubit in remote_physical_qubits if p_qubit not in self.outside_qubit_replica]
        else:
            remaining_remote_qubits = remote_physical_qubits

        if len(remaining_remote_qubits) > 0:
            # List of participating QPUs
            other_qpus = [circuit.qpus[qpu_id] for qpu_id, _ in remaining_remote_qubits]
            # Request communication qubit resources
            comm_qubit_id, comm_qubit_request = yield self.env.process(self.get_available_comm_qubit())
            # List of synchronization events
            entanglement_events = []
            for qpu in other_qpus:
                entanglement_event = self.env.event()
                self.env.process(qpu.participate_in_remote_gate(self, gate, entanglement_event))
                entanglement_events.append(entanglement_event)
            # Wait for entanglement delay
            yield self.env.timeout(ENTANGLEMENT_DELAY)
            # Wait for all QPUs to be ready
            yield simpy.events.AllOf(self.env, entanglement_events)

        # Execute the remote gate
        # TODO why not mention all logical qubits involved in the gate?
        print(f"Time {self.env.now}: QPU {self.qpu_id} executes remote gate {gate.gate_type} in circuit {circuit.circuit_id}, involving logical qubits {local_logical_qubits}")
        yield self.env.timeout(TWO_QUBIT_GATE_DELAY)
        print(f"Time {self.env.now}: QPU {self.qpu_id} completes remote gate {gate.gate_type}")


        if len(remaining_remote_qubits) > 0:
            # Record entangling operations
            self.num_total_entangled += len(entanglement_events)
            self.num_circ_entangled += len(entanglement_events)
            # Release resources in reverse order of request
            self.release_comm_qubit(comm_qubit_request)

        for req in replica_qubit_requests + data_qubit_requests:
            req.resource.release(req)

    def participate_in_remote_gate(self, initiating_qpu, gate, entanglement_event):
        circuit = gate.circuit
        # Get local logical qubits and corresponding physical qubits
        local_logical_qubits = [q for q in gate.qubits if circuit.logical_to_physical[q][0] == self.qpu_id]
        local_physical_qubits = [circuit.logical_to_physical[q][1] for q in local_logical_qubits]
        # Request resources for local physical qubits
        data_qubit_requests = [self.qubits[qubit_id].request() for qubit_id in local_physical_qubits]
        yield simpy.events.AllOf(self.env, data_qubit_requests)
        # Request communication qubit resources
        comm_qubit_id, comm_qubit_request = yield self.env.process(self.get_available_comm_qubit())
        # Wait for entanglement delay
        yield self.env.timeout(ENTANGLEMENT_DELAY)
        print(f"Time {self.env.now}: QPU {self.qpu_id} is ready to execute remote gate {gate.gate_type} with QPU {initiating_qpu.qpu_id} (circuit {circuit.circuit_id})")
        # Notify the initiating QPU that it is ready
        entanglement_event.succeed()
        # Wait for the remote gate to complete
        yield self.env.timeout(TWO_QUBIT_GATE_DELAY)
        print(f"Time {self.env.now}: QPU {self.qpu_id} completes remote gate {gate.gate_type}")
        # Release resources in reverse order
        self.release_comm_qubit(comm_qubit_request)
        for req in data_qubit_requests:
            req.resource.release(req)

    def get_available_comm_qubit(self):
        # Request an available communication qubit
        requests = []
        for qubit_id, resource in self.communication_qubits.items():
            request = resource.request()
            requests.append((qubit_id, request))
            if len(resource.queue) == 0 and len(resource.users) == 0:
                # Immediately available
                yield request
                return qubit_id, request
        # If no communication qubit is immediately available, wait for any one
        request_dict = {request: qubit_id for qubit_id, request in requests}
        result = yield simpy.events.AnyOf(self.env, [req for _, req in requests])
        request = next(iter(result.events))
        qubit_id = request_dict[request]
        return qubit_id, request

    def release_comm_qubit(self, request):
        # Release the communication qubit resource
        request.resource.release(request)

SEGMENT_FOLDER = 'segmented_circs'
def get_segmented_circuit(filename):
    with open(join(SEGMENT_FOLDER, filename), 'rb') as f:
        return load(file=f)

def set_segmented_circuit(filename, circuit_gates):
    with open(join(SEGMENT_FOLDER, filename), 'wb') as f:
        dump(circuit_gates, file=f)
    return True

class Scheduler:
    def __init__(self, env, qpus, circuits):
        self.env = env
        self.qpus = qpus
        self.circuits = circuits  # List of circuits to be scheduled
        self.action = env.process(self.run())
        self.active_circuits = []
        self.qubit_allocation = {}  # {QPU_ID: set(physical_qubit_ID)}
        for qpu_id in qpus:
            self.qubit_allocation[qpu_id] = set()
        self.max_executed_circuit_id = 0

    def segment_circuit(self, circuit_index, filename=None):
        if circuit_index >= len(self.circuits):
            return
        circ = self.circuits[circuit_index]
        lifetimes, q_idxs = get_lifetimes(input_replica=circ)
        num_qubits = max(q_idxs) + 1
        og_lifetimes = lifetimes.copy()

        qubit_segment_idx = dict({i: 0 for i in range(num_qubits)})
        def access_lifetime(qubit, delta=0):
            if not delta:
                return lifetimes[qubit][qubit_segment_idx[qubit]]
            lifetimes[qubit][qubit_segment_idx[qubit]] += delta
            return None

        _build_sync = lambda q_idx: {'type': 'SYNC', 'qubits': [q_idx]}
            
        new_gates = []
        for gate in circ:
            for qubit in gate['qubits']:
                # check if no more lifetimes exist (no need to add syncs)
                if qubit_segment_idx[qubit] >= len(lifetimes[qubit]):
                    continue

                curr_lifetime = access_lifetime(qubit)
                if curr_lifetime == 1:
                    # add sync gate for qubit
                    new_gates.append(_build_sync(qubit))
                    qubit_segment_idx[qubit] += 1
                    continue
                # decrement lifetime
                access_lifetime(qubit, delta=-1)

            new_gates.append(gate)
        
        if filename:
            set_segmented_circuit(filename=filename, circuit_gates=new_gates)

        return new_gates

    def run(self):
        def end_run():
            print(f"Time {self.env.now}: Scheduler completed a scheduling round")

        if not self.circuits:
            yield self.env.timeout(0)
            end_run()
            return

        # schedule first circuit if resources are available
        circuit_gates = self.circuits[0]
        if not self.has_enough_qubits(circuit_gates):
            print(f"Time {self.env.now}: Scheduler waiting for physical qubit resources for circuit {self.max_executed_circuit_id}")
            yield self.env.timeout(0)
            end_run()
            return

        circuit = Circuit(self.env, self.max_executed_circuit_id, circuit_gates, self.qpus, self)
        allocation_successful = self.allocate_qubits(circuit)
        print(f"Time {self.env.now}: Circuit {self.max_executed_circuit_id} allocated physical qubits {'successfully' if allocation_successful else 'unsuccessfully'}")

        if allocation_successful:
            self.circuits.pop(0)
            print(f"Time {self.env.now}: Circuit {self.max_executed_circuit_id} starts execution")
            self.max_executed_circuit_id += 1
            self.active_circuits.append(circuit)
        else:
            # This circuit will be revisited when a circuit yields scheduler.run
            print(f"Time {self.env.now}: Circuit {self.max_executed_circuit_id} waiting for physical qubit resources")
        
        yield self.env.timeout(0)
        end_run()


    def _run(self):
        circuits_to_run = []
        total_circuits_num = len(self.circuits)
        if self.circuits:
            # Keep trying to schedule circuits as long as resources are available
            while self.circuits:
                circuit_gates = self.circuits[0]

                if not self.has_enough_qubits(circuit_gates):
                    print(f"Time {self.env.now}: Scheduler waiting for physical qubit resources for circuit {self.max_executed_circuit_id}")
                    break

                circuit = Circuit(self.env, self.max_executed_circuit_id, circuit_gates, self.qpus, self)
                allocation_successful = self.allocate_qubits(circuit)
                print(f"Time {self.env.now}: Circuit {self.max_executed_circuit_id} allocated physical qubits {'successfully' if allocation_successful else 'unsuccessfully'}")

                if allocation_successful:
                    self.circuits.pop(0)
                    circuits_to_run.append(circuit)
                    print(f"Time {self.env.now}: Circuit {self.max_executed_circuit_id} starts execution")
                    self.max_executed_circuit_id += 1
                else:
                    # This circuit will be revisited when a circuit yields scheduler.run
                    print(f"Time {self.env.now}: Circuit {self.max_executed_circuit_id} waiting for physical qubit resources")
                    break
            # Execute multiple circuits simultaneously
            for circuit in circuits_to_run:
                self.active_circuits.append(circuit)

        yield self.env.timeout(0)
        print(f"Time {self.env.now}: Scheduler completed a scheduling round")

    def has_enough_qubits(self, circuit_gates):
        all_available_physical_qubits = {}
        for qpu_id, qpu in self.qpus.items():
            all_available_physical_qubits[qpu_id] = set(qpu.qubits.keys()) - self.qubit_allocation[qpu_id]

        total_available_qubits_num = sum(len(qubits) for qubits in all_available_physical_qubits.values())
        return max(qubit for gate in circuit_gates for qubit in gate['qubits']) + 1 <= total_available_qubits_num

    def allocate_qubits(self, circuit):
        # Count the number of logical qubits involved in the circuit
        num_logical_qubits = max(qubit for gate in circuit.gates for qubit in gate['qubits']) + 1
        # Allocate physical qubits for the circuit
        circuit.logical_to_physical = {}
        
        # Evenly distributes qubits, round-robin style
        for logical_qubit in range(num_logical_qubits):
            allocated = False
            for qpu_id, qpu in self.qpus.items():
                available_qubits = set(qpu.qubits.keys()) - self.qubit_allocation[qpu_id]
                if available_qubits:
                    physical_qubit = available_qubits.pop()
                    circuit.logical_to_physical[logical_qubit] = (qpu_id, physical_qubit)
                    self.qubit_allocation[qpu_id].add(physical_qubit)
                    allocated = True
                    break

            if not allocated:
                return False

        return True

    def release_qubits(self, circuit):
        # Release the physical qubits occupied by the circuit
        print(f"Time {self.env.now}: Circuit {circuit.circuit_id} releasing physical qubit resources")
        # TODO should we also remove the mapping in the logical_to_physical dict
        for qpu_id, physical_qubit in circuit.logical_to_physical.values():
            self.qubit_allocation[qpu_id].remove(physical_qubit)

def simulate(quantum_circuits, qpu_qubit_counts): 
    env = simpy.Environment()
    # Create QPUs
    qpus = {}
    for qpu_id, qubit_counts in qpu_qubit_counts.items():
        num_computing_qubits = qubit_counts['computing']
        num_communication_qubits = qubit_counts['communication']
        qpus[qpu_id] = QPU(env, qpu_id, num_computing_qubits, num_communication_qubits)

    # Create scheduler
    scheduler = Scheduler(env, qpus, quantum_circuits)
    for i in range(len(quantum_circuits)):
        print('\n'.join(str(g) for g in scheduler.segment_circuit(i, f'circ_{i}.pickle')))

    env.run()

    return env.now, sum(qpu.num_total_entangled for qpu in qpus.values())

def get_circuit_input(gate_list: list[Gate], qubit_to_node, refine_iter_cnt=3):
    if type(qubit_to_node) is list:
        qubit_to_node = {i: node for i, node in enumerate(qubit_to_node)}

    auto_gates, _, _ = full_autocomm(gate_list=gate_list, \
                               qubit_node_mapping=qubit_to_node, refine_iter_cnt=refine_iter_cnt)

    return [{'type': gate.type, 'qubits': gate.qubits, \
            'params': gate.params, 'global_phase': gate.global_phase} \
            for gate in auto_to_circ(auto_gates, qubit_to_node)]


# Example usage
if __name__ == '__main__':
    # Define quantum circuits
    quantum_circuits = [
        [
            {'type': 'H', 'qubits': [0]},
            {'type': 'CNOT', 'qubits': [0, 1]},
            {'type': 'X', 'qubits': [1]},
            {'type': 'CZ', 'qubits': [1, 2]},
        ],
        [
            {'type': 'Z', 'qubits': [0]},
            {'type': 'CNOT', 'qubits': [0, 1]},
            {'type': 'CZ', 'qubits': [0, 2]},
        ],
        [
            {'type': 'Z', 'qubits': [0]},
            {'type': 'CNOT', 'qubits': [0, 1]},
            {'type': 'CZ', 'qubits': [0, 4]},
        ],
    ]

    # Number of computing and communication qubits for each QPU
    qpu_qubit_counts = {
        'QPU1': {'computing': 4, 'communication': 1},  # QPU1 has 4 computing qubits, 1 communication qubit
        'QPU2': {'computing': 2, 'communication': 1},  # QPU2 has 3 computing qubits, 1 communication qubit
    }

    lifetime_dict, _ = get_lifetimes(input_replica=quantum_circuits[0])
    print(lifetime_dict)
    duration, entangling_ops = simulate(quantum_circuits, qpu_qubit_counts)

    print('Complete Circuit Set Simulation Stats:')
    print(f'Total time: {duration}, Num Entangling Operations: {entangling_ops}')
